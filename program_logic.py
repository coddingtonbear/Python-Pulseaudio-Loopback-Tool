import re
import subprocess
import traceback
import logging
import sys
from typing import Dict, List, Union

import pulsectl

logger = logging.getLogger("Main")


def log_exception_handler(error_type, value, tb):
    # TODO: Unify logging errors.
    the_logger = logging.getLogger("Main")
    the_logger.critical("Uncaught exception:\n"
                        "Type: {}\n"
                        "Value: {}\n"
                        "Traceback:\n {}".format(str(error_type), str(value), "".join(traceback.format_tb(tb))))


sys.excepthook = log_exception_handler


def open_pavucontrol():
    """
    Shortcut for opening pavucontrol.
    :return:
    """
    logger.info("Opening pavucontrol.")
    subprocess.Popen("pavucontrol", shell=True, stdout=subprocess.PIPE)


def list_sources(pulseaudio: pulsectl.Pulse) -> List[pulsectl.PulseSourceInfo]:
    """
    Shortcut for the pactl list sources short command.
    :return: String output from the command.
    """
    return pulseaudio.source_list()


def list_sinks(pulseaudio: pulsectl.Pulse) -> List[pulsectl.PulseSinkInfo]:
    """
    Shortcut for the pactl list sinks short command.
    :return: String output from the command.
    """
    return pulseaudio.sink_list()


def list_modules(pulseaudio: pulsectl.Pulse) -> List[pulsectl.PulseModuleInfo]:
    """
    Shortcut for the pactl list modules short command.
    :return: String output from the command.
    """
    listable_module_names = [
        'module-null-sink',
        'module-loopback',
        'module-null-source',
        'module-remap-source',
    ]
    return [
        module for module in
        pulseaudio.module_list()
        if module.name in listable_module_names
    ]


"""
Start of information processing.
"""


def _audio_device_to_dict(device: Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]) -> dict:
    """
    Takes a tab separated string in the sequence of "ID Name Driver Specification State" and turns it into a dictionary.
    :param raw_listing_string:
    :return:
    """
    return {
        "id": device.index,
        "name": device.name,
        "driver": device.driver,
        "state": device.state._value,
        "color": color_tag(device.state._value),
        "nice_name": f"{device.index} {device.description} {device.state._value.upper()}"
    }


def get_module_attributes(module: pulsectl.PulseModuleInfo) -> Dict[str, str]:
    attributes: Dict[str, str] = {}

    matches = re.findall(r'(\S+?)=((?:"[^"+]+")|(?:[^\s]+))', module.argument)
    for k, v in matches:
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]

        attributes[k] = v

    return attributes


def _module_to_dict(module: pulsectl.PulseModuleInfo) -> Dict:
    """
    Takes a tab separated string with the bare minimum sequence of "ID ModuleType" and if applicable to the program,
    turns it into a filled out dictionary.
    :param raw_listing_string:
    :return:
    """
    printable_attributes = [
        "sink_name",
        "source_name",
        "sink",
        "source",
        "master",
    ]

    attributes = get_module_attributes(module)

    attribute_strings = []
    for name in printable_attributes:
        if name not in attributes:
            continue

        attribute_strings.append(f"{name}={attributes[name]}")

    return {
        "id": module.index,
        "name": module.name,
        "nice_name": f"{module.index} {module.name} {' '.join(attribute_strings)}",
        "color": "#323232",
    }


def color_tag(raw_state: str) -> str:
    """
    Used to translate a given state to a color usable by tkinter.
    :param state: String
    :return: String color.
    """
    state = raw_state.upper()

    if state == "RUNNING":
        output = "green"
    elif state == "IDLE":
        output = "green"
    elif state == "SUSPENDED":
        output = "yellow"
    else:
        output = "red"
    return output


def get_source_list(pulseaudio: pulsectl.Pulse) -> List[Dict]:
    """
    Shortcut to getting a list of source dictionaries.
    :return:
    """
    return list(map(_audio_device_to_dict, list_sources(pulseaudio)))


def get_sink_list(pulseaudio: pulsectl.Pulse) -> List[Dict]:
    """
    Shortcut to getting a list of sink dictionaries.
    :return:
    """
    return list(map(_audio_device_to_dict, list_sinks(pulseaudio)))


def get_module_list(pulseaudio: pulsectl.Pulse) -> List[Dict]:
    """
    Shortcut to getting a list of module dictionaries.
    :return:
    """
    return list(map( _module_to_dict, list_modules(pulseaudio)))


"""
Start of module creation.
"""


def create_loopback(source_id: str, sink_id: str):
    """
    Creates a loopback with the given source id and sink id.
    :param source_id:
    :param sink_id:
    :return: Error code from the subprocess call.
    """
    logger.info("Creating a loopback.")
    logger.debug("Creating a loopback with source {} and sink {}".format(source_id, sink_id))
    returned_value = subprocess.call("pactl load-module module-loopback sink={} source={} latency_msec=1".format(
        sink_id, source_id), shell=True, stdout=subprocess.PIPE)
    if returned_value is 1:
        logger.warning("Creation of loopback with source {} and sink {} failed!".format(source_id, sink_id))
    elif returned_value is 0:
        logger.debug("Creation of loopback with source {} and sink {} successful.".format(source_id, sink_id))
    else:
        logger.error("Creation of loopback with source {} and sink {} failed with an unexpected error: {}".format(
            source_id, sink_id, returned_value))
    return returned_value


def create_virtual_sink(sink_name: str):
    """
    Creates a virtual/null sink with the given name.
    :param sink_name:
    :return: Error code from the subprocess call.
    """
    logger.info("Creating a virtual sink.")
    logger.debug("Creation a virtual sink with name {}".format(sink_name))
    returned_value = subprocess.call("pactl load-module module-null-sink sink_name={} "
                                     "sink_properties=device.description={} rate=48000".format(sink_name, sink_name),
                                     shell=True, stdout=subprocess.PIPE)
    if returned_value is 1:
        logger.warning("Creation of virtual sink with name {} failed!".format(sink_name))
    elif returned_value is 0:
        logger.debug("Creation of virtual sink with name {} successful.".format(sink_name))
    else:
        logger.error("Creation of virtual sink with name {} failed with an unexpected error: {}".format(sink_name,
                                                                                                        returned_value))
    return returned_value


def create_remapped_source(remapped_source_name: str, source_id: str):
    logger.info("Creating a remapped source.")
    logger.debug("Creating a remapped source with the name of {} from ID of {}".format(remapped_source_name, source_id))
    returned_value = subprocess.call("pactl load-module module-remap-source master={} source_name={} "
                                     "source_properties=device.description={}".format(source_id, remapped_source_name,
                                                                                      remapped_source_name), shell=True,
                                     stdout=subprocess.PIPE)
    if returned_value is 1:
        logger.warning("Creation of remapped source with name {} and ID of {} failed!".format(remapped_source_name,
                                                                                              source_id))
    elif returned_value is 0:
        logger.warning("Creation of remapped source with name {} and ID of {} successful!".format(remapped_source_name,
                                                                                                  source_id))
    else:
        logger.warning("Creation of remapped source with name {} and ID of {} failed with an unexpected error: {}".
                       format(remapped_source_name, source_id, returned_value))
    return returned_value


def delete_module(module_id: str):
    """
    Deletes/unloads a module with the given module id.
    :param module_id:
    :return: Error code from the subprocess call.
    """
    logger.info("Removing module.")
    logger.debug("Removing module with an ID of {}".format(module_id))
    returned_value = subprocess.call("pactl unload-module {}".format(module_id), shell=True, stdout=subprocess.PIPE)
    if returned_value is 1:
        logger.warning("Removal of module with ID of {} failed!".format(module_id))
    elif returned_value is 0:
        logger.debug("Removal of module with ID of {} successful.".format(module_id))
    else:
        logger.error("Removal of module with ID of {} failed with an unexpected error: {}".format(module_id,
                                                                                                  returned_value))
    return returned_value
