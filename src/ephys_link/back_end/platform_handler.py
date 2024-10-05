# ruff: noqa: BLE001
"""Manipulator platform handler.

Responsible for performing the various manipulator commands.
Instantiates the appropriate bindings based on the platform type and uses them to perform the commands.

Usage: Instantiate PlatformHandler with the platform type and call the desired command.
"""

from uuid import uuid4

from vbl_aquarium.models.ephys_link import (
    AngularResponse,
    BooleanStateResponse,
    EphysLinkOptions,
    GetManipulatorsResponse,
    PositionalResponse,
    SetDepthRequest,
    SetDepthResponse,
    SetInsideBrainRequest,
    SetPositionRequest,
    ShankCountResponse,
)
from vbl_aquarium.models.proxy import PinpointIdResponse
from vbl_aquarium.models.unity import Vector4

from ephys_link.__about__ import __version__
from ephys_link.bindings.fake_bindings import FakeBindings
from ephys_link.bindings.mpm_bindings import MPMBinding
from ephys_link.bindings.ump_3_bindings import Ump3Bindings
from ephys_link.bindings.ump_4_bindings import Ump4Bindings
from ephys_link.util.base_bindings import BaseBindings
from ephys_link.util.common import vector4_to_array
from ephys_link.util.console import Console


class PlatformHandler:
    """Handler for platform commands."""

    def __init__(self, options: EphysLinkOptions, console: Console) -> None:
        """Initialize platform handler.

        :param options: CLI options.
        :type options: EphysLinkOptions
        """

        # Store the CLI options.
        self._options = options

        # Store the console.
        self._console = console

        # Define bindings based on platform type.
        self._bindings = self._match_platform_type(options)

        # Record which IDs are inside the brain.
        self._inside_brain: set[str] = set()

        # Generate a Pinpoint ID for proxy usage.
        self._pinpoint_id = str(uuid4())[:8]

    def _match_platform_type(self, options: EphysLinkOptions) -> BaseBindings:
        """Match the platform type to the appropriate bindings.

        :param options: CLI options.
        :type options: EphysLinkOptions
        :returns: Bindings for the specified platform type.
        :rtype: :class:`ephys_link.util.base_bindings.BaseBindings`
        """
        match options.type:
            case "ump-4":
                return Ump4Bindings()
            case "ump-3":
                return Ump3Bindings()
            case "pathfinder-mpm":
                return MPMBinding(options.mpm_port)
            case "fake":
                return FakeBindings()
            case _:
                error_message = f'Platform type "{options.type}" not recognized.'
                self._console.critical_print(error_message)
                raise ValueError(error_message)

    # Ephys Link metadata.

    @staticmethod
    def get_version() -> str:
        """Get Ephys Link's version.

        :returns: Ephys Link's version.
        :rtype: str
        """
        return __version__

    def get_pinpoint_id(self) -> PinpointIdResponse:
        """Get the Pinpoint ID for proxy usage.

        :returns: Pinpoint ID response.
        :rtype: :class:`vbl_aquarium.models.ephys_link.PinpointIDResponse`
        """
        return PinpointIdResponse(pinpoint_id=self._pinpoint_id, is_requester=False)

    def get_platform_type(self) -> str:
        """Get the manipulator platform type connected to Ephys Link.

        :returns: Platform type config identifier (see CLI options for examples).
        :rtype: str
        """
        return str(self._options.type)

    # Manipulator commands.

    async def get_manipulators(self) -> GetManipulatorsResponse:
        """Get a list of available manipulators on the current handler.

        :returns: List of manipulator IDs, number of axes, dimensions of manipulators (mm), and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.GetManipulatorsResponse`
        """
        try:
            manipulators = await self._bindings.get_manipulators()
            num_axes = await self._bindings.get_axes_count()
            dimensions = self._bindings.get_dimensions()
        except Exception as e:
            self._console.exception_error_print("Get Manipulators", e)
            return GetManipulatorsResponse(error=self._console.pretty_exception(e))
        else:
            return GetManipulatorsResponse(
                manipulators=manipulators,
                num_axes=num_axes,
                dimensions=dimensions,
            )

    async def get_position(self, manipulator_id: str) -> PositionalResponse:
        """Get the current translation position of a manipulator in unified coordinates (mm).

        :param manipulator_id: Manipulator ID.
        :type manipulator_id: str
        :returns: Current position of the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.PositionalResponse`
        """
        try:
            unified_position = self._bindings.platform_space_to_unified_space(
                await self._bindings.get_position(manipulator_id)
            )
        except Exception as e:
            self._console.exception_error_print("Get Position", e)
            return PositionalResponse(error=str(e))
        else:
            return PositionalResponse(position=unified_position)

    async def get_angles(self, manipulator_id: str) -> AngularResponse:
        """Get the current rotation angles of a manipulator in Yaw, Pitch, Roll (degrees).

        :param manipulator_id: Manipulator ID.
        :type manipulator_id: str
        :returns: Current angles of the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.AngularResponse`
        """
        try:
            angles = await self._bindings.get_angles(manipulator_id)
        except Exception as e:
            self._console.exception_error_print("Get Angles", e)
            return AngularResponse(error=self._console.pretty_exception(e))
        else:
            return AngularResponse(angles=angles)

    async def get_shank_count(self, manipulator_id: str) -> ShankCountResponse:
        """Get the number of shanks on a manipulator.

        :param manipulator_id: Manipulator ID.
        :type manipulator_id: str
        :returns: Number of shanks on the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.ShankCountResponse`
        """
        try:
            shank_count = await self._bindings.get_shank_count(manipulator_id)
        except Exception as e:
            self._console.exception_error_print("Get Shank Count", e)
            return ShankCountResponse(error=self._console.pretty_exception(e))
        else:
            return ShankCountResponse(shank_count=shank_count)

    async def set_position(self, request: SetPositionRequest) -> PositionalResponse:
        """Move a manipulator to a specified translation position in unified coordinates (mm).

        :param request: Request to move a manipulator to a specified position.
        :type request: :class:`vbl_aquarium.models.ephys_link.GotoPositionRequest`
        :returns: Final position of the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.Position`
        """
        try:
            # Disallow setting manipulator position while inside the brain.
            if request.manipulator_id in self._inside_brain:
                error_message = 'Can not move manipulator while inside the brain. Set the depth ("set_depth") instead.'
                self._console.error_print("Set Position", error_message)
                return PositionalResponse(error=error_message)

            # Move to the new position.
            final_platform_position = await self._bindings.set_position(
                manipulator_id=request.manipulator_id,
                position=self._bindings.unified_space_to_platform_space(request.position),
                speed=request.speed,
            )
            final_unified_position = self._bindings.platform_space_to_unified_space(final_platform_position)

            # Return error if movement did not reach target within tolerance.
            for index, axis in enumerate(vector4_to_array(final_unified_position - request.position)):
                # End once index is the number of axes.
                if index == await self._bindings.get_axes_count():
                    break

                # Check if the axis is within the movement tolerance.
                if abs(axis) > self._bindings.get_movement_tolerance():
                    error_message = (
                        f"Manipulator {request.manipulator_id} did not reach target"
                        f" position on axis {list(Vector4.model_fields.keys())[index]}."
                        f" Requested: {request.position}, got: {final_unified_position}."
                    )
                    self._console.error_print("Set Position", error_message)
                    return PositionalResponse(error=error_message)
        except Exception as e:
            self._console.exception_error_print("Set Position", e)
            return PositionalResponse(error=self._console.pretty_exception(e))
        else:
            return PositionalResponse(position=final_unified_position)

    async def set_depth(self, request: SetDepthRequest) -> SetDepthResponse:
        """Move a manipulator's depth translation stage to a specific value (mm).

        :param request: Request to move a manipulator to a specified depth.
        :type request: :class:`vbl_aquarium.models.ephys_link.DriveToDepthRequest`
        :returns: Final depth of the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.DriveToDepthResponse`
        """
        try:
            # Move to the new depth.
            final_platform_depth = await self._bindings.set_depth(
                manipulator_id=request.manipulator_id,
                depth=self._bindings.unified_space_to_platform_space(Vector4(w=request.depth)).w,
                speed=request.speed,
            )
            final_unified_depth = self._bindings.platform_space_to_unified_space(Vector4(w=final_platform_depth)).w

            # Return error if movement did not reach target within tolerance.
            if abs(final_unified_depth - request.depth) > self._bindings.get_movement_tolerance():
                error_message = (
                    f"Manipulator {request.manipulator_id} did not reach target depth."
                    f" Requested: {request.depth}, got: {final_unified_depth}."
                )
                self._console.error_print("Set Depth", error_message)
                return SetDepthResponse(error=error_message)
        except Exception as e:
            self._console.exception_error_print("Set Depth", e)
            return SetDepthResponse(error=self._console.pretty_exception(e))
        else:
            return SetDepthResponse(depth=final_unified_depth)

    async def set_inside_brain(self, request: SetInsideBrainRequest) -> BooleanStateResponse:
        """Mark a manipulator as inside the brain or not.

        This should restrict the manipulator's movement to just the depth axis.

        :param request: Request to set a manipulator's inside brain state.
        :type request: :class:`vbl_aquarium.models.ephys_link.InsideBrainRequest`
        :returns: Inside brain state of the manipulator and an error message if any.
        :rtype: :class:`vbl_aquarium.models.ephys_link.BooleanStateResponse`
        """
        try:
            if request.inside:
                self._inside_brain.add(request.manipulator_id)
            else:
                self._inside_brain.discard(request.manipulator_id)
        except Exception as e:
            self._console.exception_error_print("Set Inside Brain", e)
            return BooleanStateResponse(error=self._console.pretty_exception(e))
        else:
            return BooleanStateResponse(state=request.inside)

    async def stop(self, manipulator_id: str) -> str:
        """Stop a manipulator.

        :param manipulator_id: Manipulator ID.
        :type manipulator_id: str
        :returns: Error message if any.
        :rtype: str
        """
        try:
            await self._bindings.stop(manipulator_id)
        except Exception as e:
            self._console.exception_error_print("Stop", e)
            return self._console.pretty_exception(e)
        else:
            return ""

    async def stop_all(self) -> str:
        """Stop all manipulators.

        :returns: Error message if any.
        :rtype: str
        """
        try:
            for manipulator_id in await self._bindings.get_manipulators():
                await self._bindings.stop(manipulator_id)
        except Exception as e:
            self._console.exception_error_print("Stop", e)
            return self._console.pretty_exception(e)
        else:
            return ""
