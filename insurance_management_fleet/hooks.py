import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Link the insured objects loaded before the module (Fase 1 and 2) to
    their fleet vehicle, by license plate or chassis number."""
    objects = env["insurance.policy.object"].sudo().search(
        [("vehicle_id", "=", False), ("policy_id.branch_id.object_type", "=", "vehicle")]
    )
    linked, skipped = objects._link_fleet_vehicles(report=True)
    _logger.info(
        "Insurance fleet: %s insured objects linked to their vehicle, %s left without vehicle (no or several matches).",
        len(linked),
        len(skipped),
    )
