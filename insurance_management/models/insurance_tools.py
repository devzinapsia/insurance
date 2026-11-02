"""Shared helpers for the insurance management models."""

from odoo.exceptions import ValidationError


def parse_alert_days(env, value):
    """Parse an alert thresholds string such as ``"30, 15,7"``.

    :param env: environment, used to translate the error message.
    :param value: comma-separated positive integers, or a falsy value.
    :return: list of distinct thresholds sorted from the largest to the
        smallest (e.g. ``[30, 15, 7]``), or an empty list when ``value`` is
        empty (meaning "inherit from the next level").
    :raise ValidationError: if any item is not a positive integer.
    """
    if not value or not value.strip():
        return []
    thresholds = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if not item.isdigit() or int(item) <= 0:
            raise ValidationError(
                env._(
                    "Alert days must be a comma-separated list of positive "
                    "whole numbers, for example 30,15,7. Invalid value: %(value)s",
                    value=item,
                )
            )
        thresholds.add(int(item))
    return sorted(thresholds, reverse=True)


def format_alert_days(env, value):
    """Return the normalized text of an alert thresholds string.

    ``" 7, 30,15 ,30"`` becomes ``"30,15,7"``; an empty value stays ``False``.
    """
    thresholds = parse_alert_days(env, value)
    return ",".join(str(days) for days in thresholds) or False
