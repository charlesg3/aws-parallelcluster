# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging
import os
from typing import List, Union

from pkg_resources import packaging

from pcluster.aws.aws_api import AWSApi
from pcluster.aws.aws_resources import ImageInfo
from pcluster.cli_commands.compute_fleet_status_manager import ComputeFleetStatus
from pcluster.models.cluster import (
    Cluster,
    ClusterActionError,
    ClusterStack,
    ClusterUpdateError,
    ConfigValidationError,
    NodeType,
)
from pcluster.models.cluster_resources import ClusterInstance
from pcluster.models.imagebuilder import ImageBuilder, ImageBuilderActionError, NonExistingImageError
from pcluster.models.imagebuilder_resources import ImageBuilderStack, NonExistingStackError
from pcluster.utils import get_installed_version, get_region
from pcluster.validators.common import FailureLevel

LOGGER = logging.getLogger(__name__)


class ApiFailure:
    """Represent a generic api error."""

    def __init__(self, message: str = None, validation_failures: list = None, update_changes: list = None):
        self.message = message or "Something went wrong."
        self.validation_failures = validation_failures or []
        self.update_changes = update_changes or []


class ClusterInfo:
    """Minimal representation of a running cluster."""

    def __init__(self, stack: ClusterStack):
        # Cluster info
        self.name = stack.cluster_name
        self.region = get_region()
        self.version = stack.version
        self.scheduler = stack.scheduler
        self.status = stack.status  # FIXME cluster status should be different from stack status
        # Stack info
        self.stack_arn = stack.id
        self.stack_name = stack.name
        self.stack_status = stack.status
        self.stack_outputs = stack.outputs

    def __repr__(self):
        return json.dumps(self.__dict__)


class ClusterInstanceInfo:
    """Minimal representation of an instance of a cluster."""

    def __init__(self, instance: ClusterInstance):
        self.launch_time = instance.launch_time
        self.instance_id = instance.id
        self.public_ip_address = instance.public_ip
        self.private_ip_address = instance.private_ip
        self.instance_type = instance.instance_type
        self.os = instance.os
        self.user = instance.default_user
        self.state = instance.state
        self.node_type = instance.node_type

    def __repr__(self):
        return json.dumps(self.__dict__)


class ImageBuilderInfo:
    """Representation common info of a building or built image."""

    def __init__(self, imagebuilder: ImageBuilder):
        self.stack_exist = False
        self.image_exist = False
        self.region = get_region()
        # image config file url
        self.image_configuration = imagebuilder.config_url


class ImageBuilderStackInfo(ImageBuilderInfo):
    """Representation stack info of a building image."""

    def __init__(self, imagebuilder: ImageBuilder, stack: ImageBuilderStack):
        super().__init__(imagebuilder=imagebuilder)
        self.stack_exist = True
        self.stack_name = stack.name
        self.stack_status = stack.status
        self.stack_arn = stack.id
        self.tags = stack.tags
        self.version = stack.version
        self.creation_time = stack.creation_time
        self.build_log = stack.build_log

        # build image process status by stack status mapping
        self.imagebuild_status = imagebuilder.imagebuild_status

    def __repr__(self):
        return json.dumps(self.__dict__)


class ImageBuilderImageInfo(ImageBuilderInfo):
    """Representation image info of a built image."""

    def __init__(self, imagebuilder: ImageBuilder, image: ImageInfo):
        super().__init__(imagebuilder=imagebuilder)
        self.image_exist = True
        self.image_name = image.name
        self.image_id = image.id
        self.image_state = image.state
        self.image_architecture = image.architecture
        self.image_tags = image.tags
        self.imagebuild_status = "BUILD_COMPLETE"
        self.creation_time = image.creation_date
        self.build_log = image.build_log
        self.version = image.version

    def __repr__(self):
        return json.dumps(self.__dict__)


class PclusterApi:
    """Proxy class for all Pcluster API commands used in the CLI."""

    def __init__(self):
        pass

    @staticmethod
    def create_cluster(
        cluster_config: dict,
        cluster_name: str,
        region: str,
        disable_rollback: bool = False,
        suppress_validators: bool = False,
        validation_failure_level: FailureLevel = FailureLevel.ERROR,
    ):
        """
        Load cluster model from cluster_config and create stack.

        :param cluster_config: cluster configuration (yaml dict)
        :param cluster_name: the name to assign to the cluster
        :param region: AWS region
        :param disable_rollback: Disable rollback in case of failures
        :param suppress_validators: Disable validator execution
        :param validation_failure_level: Min validation level that will cause the creation to fail
        """
        try:
            # Generate model from config dict and validate
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            cluster = Cluster(cluster_name, cluster_config)
            cluster.create(disable_rollback, suppress_validators, validation_failure_level)
            return ClusterInfo(cluster.stack)
        except ConfigValidationError as e:
            return ApiFailure(str(e), validation_failures=e.validation_failures)
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def delete_cluster(cluster_name: str, region: str, keep_logs: bool = True):
        """Delete cluster."""
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            # retrieve cluster config and generate model
            cluster = Cluster(cluster_name)
            cluster.delete(keep_logs)
            return ClusterInfo(cluster.stack)
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def describe_cluster(cluster_name: str, region: str):
        """Get cluster information."""
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            cluster = Cluster(cluster_name)
            return ClusterInfo(cluster.stack)
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def update_cluster(
        cluster_config: dict,
        cluster_name: str,
        region: str,
        suppress_validators: bool = False,
        validation_failure_level: FailureLevel = FailureLevel.ERROR,
        force: bool = False,
    ):
        """
        Update existing cluster.

        :param cluster_config: cluster configuration (yaml dict)
        :param cluster_name: the name to assign to the cluster
        :param region: AWS region
        :param suppress_validators: bool = False,
        :param validation_failure_level: FailureLevel = FailureLevel.ERROR,
        :param force: set to True to force stack update
        """
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            # Check if stack version matches with running version.
            cluster = Cluster(cluster_name)

            installed_version = get_installed_version()
            if cluster.stack.version != installed_version:
                raise ClusterActionError(
                    "The cluster was created with a different version of "
                    f"ParallelCluster: {cluster.stack.version}. Installed version is {installed_version}. "
                    "This operation may only be performed using the same ParallelCluster "
                    "version used to create the cluster."
                )

            cluster.update(cluster_config, suppress_validators, validation_failure_level, force)  # TODO add dryrun
            return ClusterInfo(cluster.stack)
        except ConfigValidationError as e:
            return ApiFailure(str(e), validation_failures=e.validation_failures)
        except ClusterUpdateError as e:
            return ApiFailure(str(e), update_changes=e.update_changes)
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def list_clusters(region: str):
        """List existing clusters."""
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            stacks = AWSApi.instance().cfn.list_pcluster_stacks()
            return [ClusterInfo(ClusterStack(stack)) for stack in stacks]

        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def describe_cluster_instances(
        cluster_name: str, region: str, node_type: NodeType = None
    ) -> Union[List[ClusterInstanceInfo], ApiFailure]:
        """List instances for a cluster."""
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            cluster = Cluster(cluster_name)
            instances = []
            if node_type == NodeType.HEAD_NODE or node_type is None:
                instances.append(cluster.head_node_instance)
            if node_type == NodeType.COMPUTE or node_type is None:
                instances += cluster.compute_instances

            return [ClusterInstanceInfo(instance) for instance in instances]
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def update_compute_fleet_status(cluster_name: str, region: str, status: ComputeFleetStatus):
        """Update existing compute fleet status."""
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            cluster = Cluster(cluster_name)
            if PclusterApi._is_version_2(cluster):
                raise ClusterActionError(
                    f"The cluster {cluster.name} was created with ParallelCluster {cluster.stack.version}. "
                    "This operation may only be performed using the same version used to create the cluster."
                )
            if status == ComputeFleetStatus.START_REQUESTED:
                cluster.start()
            elif status == ComputeFleetStatus.STOP_REQUESTED:
                cluster.stop()
            else:
                return ApiFailure(f"Unable to update the compute fleet to status {status}. Not supported.")

        except Exception as e:
            return ApiFailure(str(e))

        return None

    @staticmethod
    def _is_version_2(cluster):
        return packaging.version.parse(cluster.stack.version) < packaging.version.parse("3.0.0")

    @staticmethod
    def build_image(imagebuilder_config: dict, image_name: str, region: str, disable_rollback: bool = True):
        """
        Load imagebuilder model from imagebuilder_config and create stack.

        :param imagebuilder_config: imagebuilder configuration (yaml dict)
        :param image_name: the image name(the same as cfn stack name)
        :param region: AWS region
        :param disable_rollback: Disable rollback in case of failures
        """
        try:
            # Generate model from imagebuilder config dict
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            imagebuilder = ImageBuilder(image_name=image_name, config=imagebuilder_config)
            imagebuilder.create(disable_rollback)
            return ImageBuilderStackInfo(imagebuilder=imagebuilder, stack=imagebuilder.stack)
        except ImageBuilderActionError as e:
            return ApiFailure(str(e), e.validation_failures)
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def delete_image(image_name: str, region: str, force: bool = False):
        """
        Delete image and imagebuilder stack.

        :param image_name: the image name(the same as cfn stack name)
        :param region: AWS region
        :param force: Delete image even if the image is shared or instance is using it
        """
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            # retrieve imagebuilder config and generate model
            imagebuilder = ImageBuilder(image_name=image_name)
            imagebuilder.delete(force=force)
            try:
                return ImageBuilderImageInfo(imagebuilder=imagebuilder, image=imagebuilder.image)
            except NonExistingImageError:
                try:
                    return ImageBuilderStackInfo(imagebuilder=imagebuilder, stack=imagebuilder.stack)
                except NonExistingStackError:
                    raise ImageBuilderActionError(f"Image {image_name} does not exist.")
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def describe_image(image_name: str, region: str):
        """
        Get image information.

        :param image_name: the image name(the same as cfn stack name)
        :param region: AWS region
        """
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            imagebuilder = ImageBuilder(image_name=image_name)
            try:
                return ImageBuilderImageInfo(imagebuilder=imagebuilder, image=imagebuilder.image)
            except NonExistingImageError:
                try:
                    return ImageBuilderStackInfo(imagebuilder=imagebuilder, stack=imagebuilder.stack)
                except NonExistingStackError:
                    raise ImageBuilderActionError(f"Image {image_name} does not exist.")
        except Exception as e:
            return ApiFailure(str(e))

    @staticmethod
    def list_images(region: str):
        """
        List existing images.

        :param region: AWS region
        :return list
        """
        try:
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region

            # get built images by image name tag
            images = AWSApi.instance().ec2.get_images()
            imagebuilders = [ImageBuilder(image=image, image_name=image.original_image_name) for image in images]
            images_response = [
                ImageBuilderImageInfo(imagebuilder=imagebuilder, image=imagebuilder.image)
                for imagebuilder in imagebuilders
            ]

            # get building image stacks by image name tag
            imagebuilder_stacks = [
                ImageBuilder(image_name=stack.get("StackName"), stack=ImageBuilderStack(stack))
                for stack in AWSApi.instance().cfn.get_imagebuilder_stacks()
            ]
            imagebuilder_stacks_response = [
                ImageBuilderStackInfo(imagebuilder=imagebuilder, stack=imagebuilder.stack)
                for imagebuilder in imagebuilder_stacks
            ]

            return images_response + imagebuilder_stacks_response
        except Exception as e:
            return ApiFailure(str(e))