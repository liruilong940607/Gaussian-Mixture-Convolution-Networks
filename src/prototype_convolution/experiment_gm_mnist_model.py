from __future__ import print_function
import pathlib
import random

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data
import typing

import prototype_convolution.config as default_gmcn_config
import gmc.mixture as gm
import prototype_convolution.gm_modules as gm_modules


class Net(nn.Module):
    def __init__(self,
                 name: str = "default",
                 learn_positions: bool = False,
                 learn_covariances: bool = False,
                 batch_norm_per_layer: bool = False,
                 gmcn_config=default_gmcn_config):
        super(Net, self).__init__()
        self.storage_path = gmcn_config.data_base_path / "weights" / f"mnist_gmcnet_{name}.pt"
        # reference_fitter = gm_modules.generate_default_fitting_module
        n_in_g = gmcn_config.mnist_n_in_g
        n_layers_1 = gmcn_config.mnist_n_layers_1
        n_out_g_1 = gmcn_config.mnist_n_out_g_1
        n_layers_2 = gmcn_config.mnist_n_layers_2
        n_out_g_2 = gmcn_config.mnist_n_out_g_2
        n_out_g_3 = gmcn_config.mnist_n_out_g_3
        n_kernel_components = gmcn_config.mnist_n_kernel_components

        self.gmc1 = gm_modules.GmConvolution(n_layers_in=1, n_layers_out=n_layers_1, n_kernel_components=n_kernel_components,
                                             position_range=2, covariance_range=0.5,
                                             learn_positions=learn_positions, learn_covariances=learn_covariances,
                                             weight_sd=0.4)
        # self.maxPool1 = gm_modules.MaxPooling(10)

        self.gmc2 = gm_modules.GmConvolution(n_layers_in=n_layers_1, n_layers_out=n_layers_2, n_kernel_components=n_kernel_components,
                                             position_range=4, covariance_range=2,
                                             learn_positions=learn_positions, learn_covariances=learn_covariances,
                                             weight_sd=0.04)
        # self.maxPool2 = gm_modules.MaxPooling(10)

        self.gmc3 = gm_modules.GmConvolution(n_layers_in=n_layers_2, n_layers_out=10, n_kernel_components=n_kernel_components,
                                             position_range=8, covariance_range=4,
                                             learn_positions=learn_positions, learn_covariances=learn_covariances,
                                             weight_sd=0.025)
        # self.maxPool3 = gm_modules.MaxPooling(2)

        self.bn0 = gm_modules.BatchNorm(per_mixture_norm=True)
        self.bn = gm_modules.BatchNorm(per_mixture_norm=False, per_layer_norm=batch_norm_per_layer)

        # initialise these last, so all the kernels should have the same random seed
        self.relus = torch.nn.modules.ModuleList()
        self.relus.append(gm_modules.GmBiasAndRelu(layer_id="1c", n_layers=n_layers_1, n_input_gaussians=n_in_g * n_kernel_components, n_output_gaussians=n_out_g_1))
        self.relus.append(gm_modules.GmBiasAndRelu(layer_id="2c", n_layers=n_layers_2, n_input_gaussians=n_out_g_1 * n_layers_1 * n_kernel_components, n_output_gaussians=n_out_g_2))
        self.relus.append(gm_modules.GmBiasAndRelu(layer_id="3c", n_layers=10, n_input_gaussians=n_out_g_2 * n_layers_2 * n_kernel_components, n_output_gaussians=n_out_g_3))

    def set_position_learning(self, flag: bool):
        self.gmc1.learn_positions = flag
        self.gmc2.learn_positions = flag
        self.gmc3.learn_positions = flag

    def set_covariance_learning(self, flag: bool):
        self.gmc1.learn_covariances = flag
        self.gmc2.learn_covariances = flag
        self.gmc3.learn_covariances = flag

    def regularisation_loss(self):
        return self.gmc1.regularisation_loss() + self.gmc2.regularisation_loss() + self.gmc3.regularisation_loss()

    def forward(self, in_x: torch.Tensor):
        # Andrew Ng says that most of the time batch norm (BN) is applied before activation.
        # That would allow to merge the beta and bias learnable parameters
        # https://www.youtube.com/watch?v=tNIpEZLv_eg
        # Other sources recommend to applie BN after the activation function.
        #
        # in our case: BN just scales and centres. the constant input to BN is ignored, so the constant convolution would be ignored if we place BN before ReLU.
        # but that might perform better anyway, we'll have to test.
        x, x_const = self.bn0(in_x)

        x, x_const = self.gmc1(x, x_const)
        x, x_const = self.relus[0](x, x_const)
        x, x_const = self.bn(x, x_const)
        # x = self.maxPool1(x)

        x, x_const = self.gmc2(x, x_const)
        x, x_const = self.relus[1](x, x_const)
        x, x_const = self.bn(x, x_const)
        # x = self.maxPool2(x)

        x, x_const = self.gmc3(x, x_const)
        x, x_const = self.relus[2](x, x_const)
        x, x_const = self.bn(x, x_const)
        # x = self.maxPool3(x)

        x = gm.integrate(x)
        x = F.log_softmax(x, dim=1)
        return x.view(-1, 10)

    def save_model(self):
        print(f"experiment_gm_mnist_model.Net.save: saving model to {self.storage_path}")
        whole_state_dict = self.state_dict()
        filtered_state = dict()
        for name, param in whole_state_dict.items():
            if "gm_fitting_net_666" not in name:
                filtered_state[name] = param
        torch.save(self.state_dict(), self.storage_path)

    # will load kernels and biases and fitting net params (if available)
    def load(self):
        print(f"experiment_gm_mnist_model.Net.load: trying to load {self.storage_path}")
        if pathlib.Path(self.storage_path).is_file():
            whole_state_dict = torch.load(self.storage_path, map_location=torch.device('cpu'))
            filtered_state = dict()
            for name, param in whole_state_dict.items():
                if "gm_fitting_net_666" not in name:
                    filtered_state[name] = param

            missing_keys, unexpected_keys = self.load_state_dict(filtered_state, strict=False)
            print(f"experiment_gm_mnist_model.Net.load: loaded (missing: {missing_keys}")  # we routinely have unexpected keys due to filtering
        else:
            print("experiment_gm_mnist_model.Net.load: not found")

    def to(self, device: torch.device):
        return super(Net, self).to(device)
