import pathlib
import os
import sys
import typing

import gmc.modules


class Layer:
    def __init__(self, n_feature_maps, kernel_radius, n_fitting_components):
        self.n_feature_layers = n_feature_maps
        self.kernel_radius = kernel_radius
        self.n_fitting_components = n_fitting_components


def produce_name(layers: typing.List[Layer]) -> str:
    name = "L"
    for l in layers:
        name = f"{name}_{l.n_feature_layers}f_{int(l.kernel_radius * 10)}r_{int(l.n_fitting_components)}c"
    return name


class Config:
    BN_CONSTANT_COMPUTATION_ZERO = 0
    BN_CONSTANT_COMPUTATION_MEAN_IN_CONST = 1
    BN_CONSTANT_COMPUTATION_INTEGRAL = 2
    BN_CONSTANT_COMPUTATION_WEIGHTED = 3

    BIAS_TYPE_NONE = 0
    BIAS_TYPE_NORMAL = 1
    BIAS_TYPE_NEGATIVE_SOFTPLUS = 2

    BN_TYPE_ONLY_INTEGRAL = "Int"
    BN_TYPE_ONLY_COVARIANCE = "Cov"
    BN_TYPE_COVARIANCE_INTEGRAL = "CovInt"
    BN_TYPE_INTEGRAL_COVARIANCE = "IntCov"

    BN_PLACE_NOWHERE = "None"
    BN_PLACE_AFTER_GMC = "aCn"
    BN_PLACE_AFTER_RELU = "aRl"

    def __init__(self, gmms_fitting: str = "fpsmax64_2", gengmm_path: typing.Optional[str] = None, n_classes: int = 10):
        # data sources
        self.source_dir = os.path.dirname(__file__)
        self.data_base_path = pathlib.Path(f"{self.source_dir}/../../data")
        if gengmm_path is None:
            self.modelnet_data_path = pathlib.Path(f"{self.data_base_path}/modelnet/gmms/{gmms_fitting}")
        else:
            self.modelnet_data_path = pathlib.Path(f"{gengmm_path}/{gmms_fitting}")
        self.modelnet_category_list_file = pathlib.Path(f"{self.data_base_path}/modelnet/pointclouds/modelnet{n_classes}_shape_names.txt")
        self.modelnet_training_sample_names_file = pathlib.Path(f"{self.data_base_path}/modelnet/pointclouds/modelnet{n_classes}_train.txt")
        self.modelnet_test_sample_names_file = pathlib.Path(f"{self.data_base_path}/modelnet/pointclouds/modelnet{n_classes}_test.txt")

        # run settings
        self.num_dataloader_workers = 24   # 0 -> main thread, otherwise number of threads. no auto available.
        # https://stackoverflow.com/questions/38634988/check-if-program-runs-in-debug-mode
        if getattr(sys, 'gettrace', None) is not None and getattr(sys, 'gettrace')():
            # running in debugger
            self.num_dataloader_workers = 0

        self.n_classes = n_classes
        self.batch_size = 21
        self.n_epochs = 80
        self.kernel_learning_rate = 0.001
        self.learn_covariances_after = 0
        self.learn_positions_after = 0

        # complexity / power / number of parameters
        self.n_kernel_components = 5
        self.layers: typing.List[Layer] = [Layer(8, 1, 32),
                                           Layer(16, 1, 16),
                                           Layer(-1, 1, -1)]
        self.bias_type = Config.BIAS_TYPE_NONE

        # auxiliary architectural options
        self.bn_mean_over_layers = False
        self.bn_constant_computation = Config.BN_CONSTANT_COMPUTATION_ZERO
        self.bn_place = Config.BN_PLACE_AFTER_RELU
        self.bn_type = Config.BN_TYPE_COVARIANCE_INTEGRAL
        self.weight_decay_rate = 0.05

        self.relu_config: gmc.modules.ReLUFittingConfig = gmc.modules.ReLUFittingConfig()
        self.convolution_config: gmc.modules.ConvolutionConfig = gmc.modules.ConvolutionConfig(dropout=0.1)

        # logging
        self.save_model = False
        self.log_interval = self.batch_size * 10
        self.log_tensorboard_renderings = True
        self.fitting_test_data_store_at_epoch = 10000
        self.fitting_test_data_store_n_batches = 10
        self.fitting_test_data_store_path = f"{self.data_base_path}/modelnet/fitting_input"

    def produce_description(self):
        return f"BN{self.bn_place}{self.bn_type}_drp{int(self.convolution_config.dropout * 100)}_wDec{int(self.weight_decay_rate * 100)}_b{self.batch_size}_nK{self.n_kernel_components}_{produce_name(self.layers)}"

