#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
#  with the License. A copy of the License is located at http://aws.amazon.com/apache2.0/
#  or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
#  limitations under the License.


class TestParallelClusterCli:
    def test_helper(self, test_datadir, run_cli, assert_out_err):
        command = ["pcluster", "--help"]
        run_cli(command, expect_failure=False)

        assert_out_err(expected_out=(test_datadir / "pcluster-help.txt").read_text().strip(), expected_err="")

    def test_no_command(self, test_datadir, run_cli, assert_out_err):
        command = ["pcluster"]
        run_cli(command, expect_failure=True)

        assert_out_err(expected_out="", expected_err=(test_datadir / "pcluster-command-error.txt").read_text().strip())
