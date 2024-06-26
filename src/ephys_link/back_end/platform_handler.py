from typing import TYPE_CHECKING

from vbl_aquarium.models.ephys_link import (
    AngularResponse,
    BooleanStateResponse,
    DriveToDepthRequest,
    DriveToDepthResponse,
    GetManipulatorsResponse,
    GotoPositionRequest,
    InsideBrainRequest,
    PositionalResponse,
    ShankCountResponse,
)

from ephys_link.__main__ import console
from ephys_link.platforms.ump_4_bindings import Ump4Bindings
from ephys_link.util.base_commands import BaseCommands

if TYPE_CHECKING:
    from ephys_link.util.base_bindings import BaseBindings


class PlatformHandler(BaseCommands):
    """Handler for platform commands."""

    def __init__(self, platform_type: str) -> None:
        """Initialize platform handler.

        :param platform_type: Platform type to initialize bindings from.
        :type platform_type: str
        """

        # Define bindings based on platform type.
        match platform_type:
            case "ump-4":
                self._bindings: BaseBindings = Ump4Bindings()

        # Record which IDs are inside the brain.
        self._inside_brain: set[str] = set()

    async def get_manipulators(self) -> GetManipulatorsResponse:
        try:
            return GetManipulatorsResponse(
                manipulators=self._bindings.get_manipulators(),
                num_axes=self._bindings.get_num_axes(),
                dimensions=self._bindings.get_dimensions(),
            )
        except Exception as e:
            console.exception_error_print("Get Manipulators", e)
            return GetManipulatorsResponse(error=console.pretty_exception(e))

    async def get_position(self, manipulator_id: str) -> PositionalResponse:
        try:
            return PositionalResponse(
                position=self._bindings.platform_space_to_unified_space(self._bindings.get_position(manipulator_id)),
            )
        except Exception as e:
            console.exception_error_print("Get Position", e)
            return PositionalResponse(error=str(e))

    async def get_angles(self, manipulator_id: str) -> AngularResponse:
        try:
            return AngularResponse(
                angles=self._bindings.get_angles(manipulator_id),
            )
        except Exception as e:
            console.exception_error_print("Get Angles", e)
            return AngularResponse(error=console.pretty_exception(e))

    async def get_shank_count(self, manipulator_id: str) -> ShankCountResponse:
        try:
            return ShankCountResponse(shank_count=self._bindings.get_shank_count(manipulator_id))
        except Exception as e:
            console.exception_error_print("Get Shank Count", e)
            return ShankCountResponse(error=console.pretty_exception(e))

    async def set_position(self, request: GotoPositionRequest) -> PositionalResponse:
        try:
            # Disallow setting manipulator position while inside the brain.
            if request.manipulator_id in self._inside_brain:
                error_message = 'Can not move manipulator while inside the brain. Set depth ("set_depth") instead.'
                console.error_print(error_message)
                return PositionalResponse(error=error_message)

            return PositionalResponse(
                position=await self._bindings.set_position(
                    request.manipulator_id,
                    self._bindings.unified_space_to_platform_space(request.position),
                    request.position,
                )
            )
        except Exception as e:
            console.exception_error_print("Set Position", e)
            return PositionalResponse(error=console.pretty_exception(e))

    async def set_depth(self, request: DriveToDepthRequest) -> DriveToDepthResponse:
        pass

    async def set_inside_brain(self, request: InsideBrainRequest) -> BooleanStateResponse:
        try:
            if request.inside:
                self._inside_brain.add(request.manipulator_id)
            else:
                self._inside_brain.discard(request.manipulator_id)
            return BooleanStateResponse(state=request.inside)
        except Exception as e:
            console.exception_error_print("Set Inside Brain", e)
            return BooleanStateResponse(error=console.pretty_exception(e))

    async def calibrate(self, manipulator_id: str) -> str:
        try:
            return await self._bindings.calibrate(manipulator_id)
        except Exception as e:
            console.exception_error_print("Calibrate", e)
            return console.pretty_exception(e)

    async def stop(self) -> str:
        try:
            return await self._bindings.stop()
        except Exception as e:
            console.exception_error_print("Stop", e)
            return console.pretty_exception(e)
