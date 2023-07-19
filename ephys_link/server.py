"""WebSocket server and communication handler

Manages the WebSocket server and handles connections and events from the client. For
every event, the server does the following:

1. Extract the arguments passed in the event
2. Log that the event was received
3. Call the appropriate function in :mod:`ephys_link.sensapex_handler` with arguments
4. Relay the response from :mod:`ephys_link.sensapex_handler` to the callback function
"""

import argparse
import importlib
import signal
import time
from threading import Event, Thread
from tkinter import Tk
from typing import Any

import common as com

# noinspection PyPackageRequirements
import socketio
from aiohttp import web
from aiohttp.web_runner import GracefulExit
from gui import GUI
from platform_handler import PlatformHandler
from pythonnet import load
from serial import Serial
from serial.tools.list_ports import comports

# Setup server
load("netfx")
sio = socketio.AsyncServer()
app = web.Application()
sio.attach(app)
is_connected = False

# Declare platform handler
platform: PlatformHandler

# Setup argument parser
parser = argparse.ArgumentParser(
    description="Electrophysiology Manipulator Link: a websocket interface for"
    " manipulators in electrophysiology experiments",
    prog="python -m ephys-link",
)
parser.add_argument("-g", "--gui", dest="gui", action="store_true", help="Launches GUI")
parser.add_argument(
    "-t",
    "--type",
    type=str,
    dest="type",
    default="sensapex",
    help='Manipulator type (i.e. "sensapex" or "new_scale"). Default: "sensapex"',
)
parser.add_argument(
    "-d", "--debug", dest="debug", action="store_true", help="Enable debug mode"
)
parser.add_argument(
    "-p",
    "--port",
    type=int,
    default=8081,
    dest="port",
    help="Port to serve on. Default: 8081 (avoids conflict with other HTTP servers)",
)
parser.add_argument(
    "-s",
    "--serial",
    type=str,
    default="no-e-stop",
    dest="serial",
    nargs="?",
    help="Emergency stop serial port (i.e. COM3). Default: disables emergency stop",
)
parser.add_argument(
    "--version",
    action="version",
    version="Electrophysiology Manipulator Link v0.1",
    help="Print version and exit",
)

# Is the server running
is_running = False

# Setup Arduino serial port
poll_rate = 0.05
kill_serial_event = Event()
poll_serial_thread: Thread


def poll_serial(kill_event: Event, serial_port: str) -> None:
    """Continuously poll serial port for data

    :param kill_event: Event to stop polling
    :type kill_event: Event
    :param serial_port: The serial port to poll
    :type serial_port: str
    :return: None
    """
    target_port = serial_port
    if serial_port is None:
        # Search for serial ports
        for port, desc, _ in comports():
            if "Arduino" in desc or "USB Serial Device" in desc:
                target_port = port
                break
    elif serial_port == "no-e-stop":
        # Stop polling if no-e-stop is specified
        return None

    ser = Serial(target_port, 9600, timeout=poll_rate)
    while not kill_event.is_set():
        if ser.in_waiting > 0:
            ser.readline()
            # Cause a break
            com.dprint("[EMERGENCY STOP]\t\t Stopping all manipulators")
            platform.stop()
            ser.reset_input_buffer()
        time.sleep(poll_rate)
    print("Close poll")
    ser.close()


# Handle connection events


@sio.event
async def connect(sid, _, __) -> bool:
    """Acknowledge connection to the server

    :param sid: Socket session ID
    :type sid: str
    :param _: WSGI formatted dictionary with request info (unused)
    :type _: dict
    :param __: Authentication details (unused)
    :type __: dict
    :return: False on error to refuse connection. None otherwise.
    :rtype: bool
    """
    print(f"[CONNECTION REQUEST]:\t\t {sid}\n")

    global is_connected
    if not is_connected:
        print(f"[CONNECTION GRANTED]:\t\t {sid}\n")
        is_connected = True
    else:
        print(f"[CONNECTION DENIED]:\t\t {sid}: another client is already connected\n")
        return False


@sio.event
async def disconnect(sid) -> None:
    """Acknowledge disconnection from the server

    :param sid: Socket session ID
    :type sid: str
    :return: None
    """
    print(f"[DISCONNECTION]:\t {sid}\n")

    platform.reset()
    global is_connected
    is_connected = False


# Events
@sio.event
async def get_manipulators(_) -> com.GetManipulatorsOutputData:
    """Get the list of discoverable manipulators

    :param _: Socket session ID (unused)
    :type _: str
    :return: Callback parameters (manipulators, error message)
    :rtype: :class:`ephys_link.common.GetManipulatorsOutputData`
    """
    com.dprint("[EVENT]\t\t Get discoverable manipulators")

    return platform.get_manipulators()


@sio.event
async def register_manipulator(_, manipulator_id: str) -> str:
    """Register a manipulator with the server

    :param _: Socket session ID (unused)
    :type _: str
    :param manipulator_id: ID of the manipulator to register
    :type manipulator_id: str
    :return: Callback parameter (Error message (on error))
    :rtype: str
    """
    com.dprint(f"[EVENT]\t\t Register manipulator: {manipulator_id}")

    return platform.register_manipulator(manipulator_id)


@sio.event
async def unregister_manipulator(_, manipulator_id: str) -> str:
    """Unregister a manipulator from the server

    :param _: Socket session ID (unused)
    :type _: str
    :param manipulator_id: ID of the manipulator to unregister
    :type manipulator_id: str
    :return: Callback parameter (Error message (on error))
    :rtype: str
    """
    com.dprint(f"[EVENT]\t\t Unregister manipulator: {manipulator_id}")

    return platform.unregister_manipulator(manipulator_id)


@sio.event
async def get_pos(_, manipulator_id: str) -> com.PositionalOutputData:
    """Position of manipulator request

    :param _: Socket session ID (unused)
    :type _: str
    :param manipulator_id: ID of manipulator to pull position from
    :type manipulator_id: str
    :return: Callback parameters (manipulator ID, position in (x, y, z, w) (or an empty
        array on error), error message)
    :rtype: :class:`ephys_link.common.PositionalOutputData`
    """
    com.dprint(f"[EVENT]\t\t Get position of manipulator" f" {manipulator_id}")

    return platform.get_pos(manipulator_id)


@sio.event
async def goto_pos(
    _, data: com.GotoPositionInputDataFormat
) -> com.PositionalOutputData:
    """Move manipulator to position

    :param _: Socket session ID (unused)
    :type _: str
    :param data: Data containing manipulator ID, position, and speed
    :type data: :class:`ephys_link.common.GotoPositionInputDataFormat`
    :return: Callback parameters (manipulator ID, position in (x, y, z, w) (or an empty
        tuple on error), error message)
    :rtype: :class:`ephys_link.common.PositionalOutputData`
    """
    try:
        manipulator_id = data["manipulator_id"]
        pos = data["pos"]
        speed = data["speed"]

    except KeyError:
        manipulator_id = data["manipulator_id"] if "manipulator_id" in data else -1
        print(f"[ERROR]\t\t Invalid data for manipulator {manipulator_id}\n")
        return com.PositionalOutputData([], "Invalid data format")

    except Exception as e:
        print(f"[ERROR]\t\t Error in goto_pos: {e}\n")
        return com.PositionalOutputData([], "Error in goto_pos")

    com.dprint(f"[EVENT]\t\t Move manipulator {manipulator_id} " f"to position {pos}")

    return await platform.goto_pos(manipulator_id, pos, speed)


@sio.event
async def drive_to_depth(
    _, data: com.DriveToDepthInputDataFormat
) -> com.DriveToDepthOutputData:
    """Drive to depth

    :param _: Socket session ID (unused)
    :type _: str
    :param data: Data containing manipulator ID, depth, and speed
    :type data: :class:`ephys_link.common.DriveToDepthInputDataFormat`
    :return: Callback parameters (manipulator ID, depth (or -1 on error), error message
        )
    :rtype: :class:`ephys_link.common.DriveToDepthOutputData`
    """
    try:
        manipulator_id = data["manipulator_id"]
        depth = data["depth"]
        speed = data["speed"]

    except KeyError:
        manipulator_id = data["manipulator_id"] if "manipulator_id" in data else -1
        print(f"[ERROR]\t\t Invalid data for manipulator {manipulator_id}\n")
        return com.DriveToDepthOutputData(-1, "Invalid data " "format")

    except Exception as e:
        print(f"[ERROR]\t\t Error in drive_to_depth: {e}\n")
        return com.DriveToDepthOutputData(-1, "Error in drive_to_depth")

    com.dprint(f"[EVENT]\t\t Drive manipulator {manipulator_id} " f"to depth {depth}")

    return await platform.drive_to_depth(manipulator_id, depth, speed)


@sio.event
async def set_inside_brain(
    _, data: com.InsideBrainInputDataFormat
) -> com.StateOutputData:
    """Set the inside brain state

    :param _: Socket session ID (unused)
    :type _: str
    :param data: Data containing manipulator ID and inside brain state
    :type data: :class:`ephys_link.common.InsideBrainInputDataFormat`
    :return: Callback parameters (manipulator ID, inside, error message)
    :rtype: :class:`ephys_link.common.StateOutputData`
    """
    try:
        manipulator_id = data["manipulator_id"]
        inside = data["inside"]

    except KeyError:
        manipulator_id = data["manipulator_id"] if "manipulator_id" in data else -1
        print(f"[ERROR]\t\t Invalid data for manipulator {manipulator_id}\n")
        return com.StateOutputData(False, "Invalid data format")
    except Exception as e:
        print(f"[ERROR]\t\t Error in inside_brain: {e}\n")
        return com.StateOutputData(False, "Error in set_inside_brain")

    com.dprint(
        f"[EVENT]\t\t Set manipulator {manipulator_id} inside brain to "
        f'{"true" if inside else "false"}'
    )

    return platform.set_inside_brain(manipulator_id, inside)


@sio.event
async def calibrate(_, manipulator_id: str) -> str:
    """Calibrate manipulator

    :param _: Socket session ID (unused)
    :type _: str
    :param manipulator_id: ID of manipulator to calibrate
    :type manipulator_id: str
    :return: Callback parameters (manipulator ID, error message)
    :rtype: str
    """
    com.dprint(f"[EVENT]\t\t Calibrate manipulator" f" {manipulator_id}")

    return await platform.calibrate(manipulator_id, sio)


@sio.event
async def bypass_calibration(_, manipulator_id: str) -> str:
    """Bypass calibration of manipulator

    :param _: Socket session ID (unused)
    :type _: str
    :param manipulator_id: ID of manipulator to bypass calibration
    :type manipulator_id: str
    :return: Callback parameters (manipulator ID, error message)
    :rtype: str
    """
    com.dprint(f"[EVENT]\t\t Bypass calibration of manipulator" f" {manipulator_id}")

    return platform.bypass_calibration(manipulator_id)


@sio.event
async def set_can_write(_, data: com.CanWriteInputDataFormat) -> com.StateOutputData:
    """Set manipulator can_write state

    :param _: Socket session ID (unused)
    :type _: str
    :param data: Data containing manipulator ID and can_write brain state
    :type data: :class:`ephys_link.common.CanWriteInputDataFormat`
    :return: Callback parameters (manipulator ID, can_write, error message)
    :rtype: :class:`ephys_link.common.StateOutputData`
    """
    try:
        manipulator_id = data["manipulator_id"]
        can_write = data["can_write"]
        hours = data["hours"]

    except KeyError:
        manipulator_id = data["manipulator_id"] if "manipulator_id" in data else -1
        print(f"[ERROR]\t\t Invalid data for manipulator {manipulator_id}\n")
        return com.StateOutputData(False, "Invalid data " "format")

    except Exception as e:
        print(f"[ERROR]\t\t Error in inside_brain: {e}\n")
        return com.StateOutputData(False, "Error in set_can_write")

    com.dprint(
        f"[EVENT]\t\t Set manipulator {manipulator_id} can_write state to "
        f'{"true" if can_write else "false"}'
    )

    return platform.set_can_write(manipulator_id, can_write, hours, sio)


@sio.event
def stop(_) -> bool:
    """Stop all manipulators

    :param _: Socket session ID (unused)
    :type _: str
    :return: True if successful, False otherwise
    :rtype: bool
    """
    com.dprint("[EVENT]\t\t Stop all manipulators")

    return platform.stop()


@sio.on("*")
async def catch_all(_, __, data: Any) -> None:
    """Catch all event

    :param _: Socket session ID (unused)
    :type _: str
    :param __: Client ID (unused)
    :type __: str
    :param data: Data received from client
    :type data: Any
    :return: None
    """
    print(f"[UNKNOWN EVENT]:\t {data}")


# Handle server start and end


def launch_server(platform_type: str, server_port: int) -> None:
    """Launch the server

    :param platform_type: Parsed argument for platform type
    :type platform_type: str
    :param server_port: HTTP port to serve the server
    :type server_port: int
    :return: None
    """

    # Import correct manipulator handler
    global platform
    match platform_type:
        case "sensapex":
            platform = importlib.import_module(
                "platforms.sensapex_handler"
            ).SensapexHandler()
        case "new_scale":
            platform = importlib.import_module(
                "platforms.new_scale_handler"
            ).NewScaleHandler()
        case "new_scale_pathway":
            platform = importlib.import_module(
                "platforms.new_scale_pathway_handler"
            ).NewScalePathwayHandler()
        case unknown_type:
            exit(f"[ERROR]\t\t Invalid manipulator type: {unknown_type}")

    # List available manipulators
    print("Available Manipulators:")
    print(platform.get_manipulators()["manipulators"])

    # Mark that server is running
    global is_running
    is_running = True
    web.run_app(app, port=server_port)


def close_server(_, __) -> None:
    """Close the server"""
    print("[INFO]\t\t Closing server")

    # Stop movement
    platform.stop()  # noqa

    # Exit
    raise GracefulExit()


def close_serial(_, __) -> None:
    """Close the serial connection"""
    print("[INFO]\t\t Closing serial")
    kill_serial_event.set()
    poll_serial_thread.join()


def start() -> None:
    """Starts everything"""

    # Parse arguments
    args = parser.parse_args()
    com.set_debug(args.debug)

    if args.gui:
        # Start GUI (doesn't launch server yet)
        root = Tk()
        GUI(root, launch_server, stop, poll_serial, args)
        root.mainloop()

    else:
        if args.serial != "no-e-stop":
            # Register serial exit
            signal.signal(signal.SIGTERM, close_serial)
            signal.signal(signal.SIGINT, close_serial)

            # Start emergency stop system if serial is provided
            global poll_serial_thread
            poll_serial_thread = Thread(
                target=poll_serial,
                args=(
                    kill_serial_event,
                    args.serial,
                ),
                daemon=True,
            )
            poll_serial_thread.start()

        # Register server exit
        signal.signal(signal.SIGTERM, close_server)
        signal.signal(signal.SIGINT, close_server)

        # Launch with parsed arguments on main thread
        launch_server(args.type, args.port)


if __name__ == "__main__":
    start()
