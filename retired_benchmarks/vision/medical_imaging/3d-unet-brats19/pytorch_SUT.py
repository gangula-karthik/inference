# coding=utf-8
# Copyright (c) 2020 NVIDIA CORPORATION. All rights reserved.
# Copyright 2020 Division of Medical Image Computing, German Cancer Research Center (DKFZ), Heidelberg, Germany
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import array
import json
import os
import sys

sys.path.insert(0, os.getcwd())


sys.path.insert(0, os.path.join(os.getcwd(), "nnUnet"))

try:
    from nnunet.training.model_restore import load_model_and_checkpoint_files
    from brats_QSL import get_brats_QSL
    import torch.nn.functional as F
    import torch
    import numpy as np
    import mlperf_loadgen as lg
except BaseException:
    raise Exception("Error importing local modules")


class _3DUNET_PyTorch_SUT:
    def __init__(
        self,
        model_dir,
        preprocessed_data_dir,
        performance_count,
        folds,
        checkpoint_name,
    ):

        print("Loading PyTorch model...")
        model_path = os.path.join(model_dir, "plans.pkl")
        assert os.path.isfile(model_path), "Cannot find the model file {:}!".format(
            model_path
        )
        self.trainer, params = load_model_and_checkpoint_files(
            model_dir, folds, fp16=False, checkpoint_name=checkpoint_name
        )
        self.trainer.load_checkpoint_ram(params[0], False)
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

        print("Constructing SUT...")
        self.sut = lg.ConstructSUT(self.issue_queries, self.flush_queries)
        print("Finished constructing SUT.")
        self.qsl = get_brats_QSL(preprocessed_data_dir, performance_count)

    def issue_queries(self, query_samples):
        with torch.no_grad():
            for i in range(len(query_samples)):
                data = self.qsl.get_features(query_samples[i].index)

                print(
                    "Processing sample id {:d} with shape = {:}".format(
                        query_samples[i].index, data.shape
                    )
                )

                image = torch.from_numpy(
                    data[np.newaxis, ...]).float().to(self.device)
                output = self.trainer.network(
                    image)[0].cpu().numpy().astype(np.float16)

                transpose_forward = self.trainer.plans.get("transpose_forward")
                transpose_backward = self.trainer.plans.get(
                    "transpose_backward")
                assert transpose_forward == [
                    0,
                    1,
                    2,
                ], "Unexpected transpose_forward {:}".format(transpose_forward)
                assert transpose_backward == [
                    0,
                    1,
                    2,
                ], "Unexpected transpose_backward {:}".format(transpose_backward)

                response_array = array.array("B", output.tobytes())
                bi = response_array.buffer_info()
                response = lg.QuerySampleResponse(
                    query_samples[i].id, bi[0], bi[1])
                lg.QuerySamplesComplete([response])

    def flush_queries(self):
        pass


def get_pytorch_sut(
    model_dir,
    preprocessed_data_dir,
    performance_count,
    folds=1,
    checkpoint_name="model_final_checkpoint",
):
    return _3DUNET_PyTorch_SUT(
        model_dir, preprocessed_data_dir, performance_count, folds, checkpoint_name
    )
