"""
    ParallelCluster

    ParallelCluster API  # noqa: E501

    The version of the OpenAPI document: 3.0.0
    Generated by: https://openapi-generator.tech
"""


import unittest

import pcluster.api.client
from pcluster.api.client.api.cluster_instances_api import ClusterInstancesApi  # noqa: E501


class TestClusterInstancesApi(unittest.TestCase):
    """ClusterInstancesApi unit test stubs"""

    def setUp(self):
        self.api = ClusterInstancesApi()  # noqa: E501

    def tearDown(self):
        pass

    def test_delete_cluster_instances(self):
        """Test case for delete_cluster_instances

        """
        pass

    def test_describe_cluster_instances(self):
        """Test case for describe_cluster_instances

        """
        pass


if __name__ == '__main__':
    unittest.main()