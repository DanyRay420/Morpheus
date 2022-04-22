# Copyright (c) 2021-2022, NVIDIA CORPORATION.
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
"""
Contains configuration objects used to run pipeline and utilities.
"""

import dataclasses
import json
import logging
import typing
from enum import Enum

logger = logging.getLogger(__name__)


def auto_determine_bootstrap():
    """Auto determine bootstrap servers for kafka cluster."""
    import docker

    kafka_compose_name = "kafka-docker"

    docker_client = docker.from_env()
    bridge_net = docker_client.networks.get("bridge")
    bridge_ip = bridge_net.attrs["IPAM"]["Config"][0]["Gateway"]

    kafka_net = docker_client.networks.get(kafka_compose_name + "_default")

    bootstrap_servers = ",".join([
        c.ports["9092/tcp"][0]["HostIp"] + ":" + c.ports["9092/tcp"][0]["HostPort"] for c in kafka_net.containers
        if "9092/tcp" in c.ports
    ])

    # Use this version to specify the bridge IP instead
    bootstrap_servers = ",".join(
        [bridge_ip + ":" + c.ports["9092/tcp"][0]["HostPort"] for c in kafka_net.containers if "9092/tcp" in c.ports])

    logger.info("Auto determined Bootstrap Servers: {}".format(bootstrap_servers))

    return bootstrap_servers


@dataclasses.dataclass
class ConfigBase():
    """This is the base class for pipeline configuration."""
    pass


@dataclasses.dataclass
class ConfigOnnxToTRT(ConfigBase):
    """
    Configuration class for the OnnxToTRT migration process.

    Parameters
    ----------
    input_model : str
        Input ONNX model file.
    output_model : str
        Output TensorRT model file.
    batches : typing.List[typing.Tuple[int, int]]
        Batches of input data.
    seq_length : int
        Sequence length.
    max_workspace_size : int
        Maximum workspace size, default 16000 MB.

    Attributes
    ----------
    input_model : str
        Input ONNX model file.
    output_model : str
        Output TensorRT model file.
    seq_length : int
        Sequence length.

    """
    input_model: str = None
    output_model: str = None
    batches: typing.List[typing.Tuple[int, int]] = dataclasses.field(default_factory=list)
    seq_length: int = None
    max_workspace_size: int = 16000  # In MB


@dataclasses.dataclass
class ConfigAutoEncoder(ConfigBase):
    """
    AutoEncoder configuration class.

    Parameters
    ----------
    use_processes : bool
        Not currently used.

    Attributes
    ----------
    feature_columns : typing.List[str]
        CloudTrail feature columns.
    userid_column_name : str
        Userid column in CloudTrail logs.
    userid_filter : str
        Userid to filter on.

    """
    feature_columns: typing.List[str] = None
    userid_column_name: str = "userIdentityaccountId"
    userid_filter: str = None


@dataclasses.dataclass
class ConfigFIL(ConfigBase):
    feature_columns: typing.List[str] = None


class PipelineModes(str, Enum):
    """The type of usecases that can be executed by the pipeline is determined by the enum."""
    OTHER = "OTHER"
    NLP = "NLP"
    FIL = "FIL"
    AE = "AE"


class CppConfig:
    """
    Allows setting whether C++ implementations should be used for Morpheus stages and messages. Defaults to True,
    meaning C++ should be used where an implementation is available. Can be set to False to use Python implementations.
    This can be useful for debugging but C++ should be preferred for performance.
    """
    __use_cpp: bool = True

    @staticmethod
    def get_should_use_cpp() -> bool:
        """
        Gets the global option for whether to use C++ node and message types or otherwise prefer Python.
        """
        return CppConfig.__use_cpp

    @staticmethod
    def set_should_use_cpp(value: bool):
        """
        Sets the global option for whether to use C++ node and message types or otherwise prefer Python.
        """
        CppConfig.__use_cpp = value


@dataclasses.dataclass
class Config(ConfigBase):
    """
    Pipeline configuration class.

    Parameters
    ----------
    debug : bool
        Flag to run pipeline in debug mode. Default value is False.
    log_level : int
        Specifies the log level and above to output. Must be one of the available levels in the `logging` module.
    mode : `PipelineModes`
        Determines type of pipeline Ex: FIL or NLP. Use `OTHER` for custom pipelines.
    feature_length : int
        Specifies the dimension of the second axis for messages in the pipeline. For NLP this is the sequence length.
        For FIL this is the number of input features.
    pipeline_batch_size : int
        Determines number of messages per batch. Default value is 256.
    num_threads : int
        Number threads to process each batch of messages. Default value is 1.
    model_max_batch_size : 8
        In a single batch, the maximum number of messages to send to the model for inference. Default value is
        8.
    edge_buffer_size : int, default = 128
        The size of buffered channels to use between nodes in a pipeline. Larger values reduce backpressure at the cost
        of memory. Smaller values will push messages through the pipeline quicker. Must be greater than 1 and a power of
        2 (i.e., 2, 4, 8, 16, etc.).
    use_cpp : bool, default = True
        Whether or not to use C++ node and message types or to prefer Python. Only use as a last resort if bugs are
        encountered.

    Attributes
    ----------
    ae : `ConfigAutoEncoder`
        Config for autoencoder.
    log_config_file : str
        File corresponding to this Config.

    """
    # Whether in Debug mode.
    debug: bool = False
    log_level: int = logging.WARN
    log_config_file: str = None

    mode: PipelineModes = PipelineModes.OTHER

    feature_length: int = 256
    pipeline_batch_size: int = 256
    num_threads: int = 1
    model_max_batch_size: int = 8
    edge_buffer_size: int = 128

    # Class labels to convert class index to label.
    class_labels: typing.List[str] = dataclasses.field(default_factory=list)

    ae: ConfigAutoEncoder = dataclasses.field(default=None)
    fil: ConfigFIL = dataclasses.field(default=None)

    def save(self, filename: str):
        """
        Save Config to file.

        Parameters
        ----------
        filename : str
            File path to save Config.
        """
        # Read the json file and store as
        with open(filename, "w") as f:
            json.dump(dataclasses.asdict(self), f, indent=3, sort_keys=True)

    def to_string(self):
        """Get string representation of Config.

        Returns
        -------
        str
            Config as string.
        """
        # pp = pprint.PrettyPrinter(indent=2, width=80)

        # return pp.pformat(dataclasses.asdict(self))

        # Using JSON serializer for now since its easier to read. pprint is more compact
        return json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True)
