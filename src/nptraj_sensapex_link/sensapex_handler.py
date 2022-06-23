from manipulator import Manipulator
from pathlib import Path
from sensapex import UMP, UMError
from typing import TypedDict

# Setup Sensapex
UMP.set_library_path(str(Path(__file__).parent.absolute()) + '/resources/')
ump = UMP.get_ump()

# Registered manipulators
manipulators = {}


class GotoPositionDataFormat(TypedDict):
    manipulator_id: int
    pos: list[float]
    speed: int


class InsideBrainDataFormat(TypedDict):
    manipulator_id: int
    inside: bool


def reset() -> None:
    """Reset handler"""
    manipulators.clear()


def register_manipulator(manipulator_id: int) -> (int, str):
    """
    Register a manipulator
    :param manipulator_id: The ID of the manipulator to register.
    :return: Callback parameters [manipulator_id, error message (on error)]
    """
    # Check if manipulator is already registered
    if manipulator_id in manipulators:
        print(f'[ERROR]\t\t Manipulator already registered:'
              f' {manipulator_id}\n')
        return manipulator_id, 'Manipulator already registered'

    try:
        # Register manipulator
        manipulators[manipulator_id] = Manipulator(
            ump.get_device(manipulator_id))

        print(f'[SUCCESS]\t Registered manipulator: {manipulator_id}\n')
        return manipulator_id, ''

    except ValueError:
        # Manipulator not found in UMP
        print(f'[ERROR]\t\t Manipulator not found: {manipulator_id}\n')
        return manipulator_id, 'Manipulator not found'

    except Exception as e:
        # Other error
        print(f'[ERROR]\t\t Registering manipulator: {manipulator_id}')
        print(f'{e}\n')
        return manipulator_id, 'Error registering manipulator'


def get_pos(manipulator_id: int) -> (int, tuple[float], str):
    """
    Get the current position of a manipulator
    :param manipulator_id: The ID of the manipulator to get the position of.
    :return: Callback parameters [Manipulator ID, position in [x, y, z,
    w] (or an empty array on error), error message]
    """
    try:
        # Check calibration status
        if not manipulators[manipulator_id].get_calibrated():
            print(f'[ERROR]\t\t Calibration not complete\n')
            return manipulator_id, (), 'Manipulator not calibrated'

        # Get position
        return manipulators[manipulator_id].get_pos()

    except KeyError:
        # Manipulator not found in registered manipulators
        print(f'[ERROR]\t\t Manipulator not registered: {manipulator_id}')
        return manipulator_id, (), 'Manipulator not registered'


async def goto_pos(manipulator_id: int, position: list[float], speed: int) \
        -> (int, tuple[float], str):
    """
    Move manipulator to position
    :param manipulator_id: The ID of the manipulator to move
    :param position: The position to move to
    :param speed: The speed to move at (in um/s)
    :return: Callback parameters [Manipulator ID, position in [x, y, z,
    w] (or an empty array on error), error message]
    """
    try:
        # Check calibration status
        if not manipulators[manipulator_id].get_calibrated():
            print(f'[ERROR]\t\t Calibration not complete\n')
            return manipulator_id, (), 'Manipulator not calibrated'

        return await manipulators[manipulator_id].goto_pos(position, speed)

    except KeyError:
        # Manipulator not found in registered manipulators
        print(f'[ERROR]\t\t Manipulator not registered: {manipulator_id}\n')
        return manipulator_id, (), 'Manipulator not registered'


async def inside_brain(manipulator_id: int, inside: bool) -> (int, str):
    """
    Set manipulator inside brain status (restricts motion)
    :param manipulator_id: The ID of the manipulator to set the status of
    :param inside: True if inside brain, False if outside
    :return: Callback parameters (Manipulator ID, error message)
    """
    try:
        # Check calibration status
        if not manipulators[manipulator_id].get_calibrated():
            print(f'[ERROR]\t\t Calibration not complete\n')
            return manipulator_id, 'Manipulator not calibrated'

        manipulators[manipulator_id].set_inside_brain(inside)
        return manipulator_id, ''

    except KeyError:
        # Manipulator not found in registered manipulators
        print(f'[ERROR]\t\t Manipulator not registered: {manipulator_id}\n')
        return manipulator_id, 'Manipulator not registered'

    except Exception as e:
        # Other error
        print(f'[ERROR]\t\t Set manipulator {manipulator_id} inside brain '
              f'status')
        print(f'{e}\n')
        return manipulator_id, 'Error setting inside brain'


async def calibrate(manipulator_id: int, sio) -> (int, str):
    """
        Calibrate manipulator
        :param manipulator_id: ID of manipulator to calibrate
        :param sio: SocketIO object (to call sleep)
        :return: Callback parameters [Manipulator ID, error message]
        """
    try:
        # Move manipulator to max position
        await manipulators[manipulator_id].goto_pos([20000, 20000, 20000,
                                                     20000], 2000)

        # Call calibrate
        manipulators[manipulator_id].call_calibrate()
        await sio.sleep(70)
        manipulators[manipulator_id].set_calibrated()
        return manipulator_id, ''

    except KeyError:
        # Manipulator not found in registered manipulators
        print(f'[ERROR]\t\t Manipulator not registered: {manipulator_id}\n')
        return manipulator_id, 'Manipulator not registered'

    except UMError as e:
        # SDK call error
        print(f'[ERROR]\t\t Calling calibrate manipulator {manipulator_id}')
        print(f'{e}\n')
        return manipulator_id, 'Error calling calibrate'

    except Exception as e:
        # Other error
        print(f'[ERROR]\t\t Calibrate manipulator {manipulator_id}')
        print(f'{e}\n')
        return manipulator_id, 'Error calibrating manipulator'


def bypass_calibration(manipulator_id: int) -> (int, str):
    """
    Bypass calibration of manipulator
    :param manipulator_id: ID of manipulator to bypass calibration
    :return: Callback parameters (Manipulator ID, error message)
    """
    try:
        # Bypass calibration
        manipulators[manipulator_id].set_calibrated()
        return manipulator_id, ''

    except KeyError:
        # Manipulator not found in registered manipulators
        print(f'[ERROR]\t\t Manipulator not registered: {manipulator_id}\n')
        return manipulator_id, 'Manipulator not registered'

    except Exception as e:
        # Other error
        print(
            f'[ERROR]\t\t Bypass calibration of manipulator {manipulator_id}')
        print(f'{e}\n')
        return manipulator_id, 'Error bypassing calibration'
