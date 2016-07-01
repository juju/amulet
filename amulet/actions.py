import json

from .helpers import (
    juju,
    JUJU_VERSION,
    TimeoutError,
)


def list_actions(service):
    """Return list of actions defined for the service.

    :param service: Name of service for which to list actions.
    :return: List of actions, as json.

    """
    if JUJU_VERSION.major == 1:
        raw = juju(['action', 'defined', service, '--format', 'json'])
    else:
        raw = juju(['list-actions', service, '--format', 'json'])

    try:
        result = json.loads(raw)
    except ValueError:
        result = {}
    return result
action_defined = list_actions


def run_action(unit, action, action_args=None):
    """Run action on a unit and return the result UUID.

    :param unit: Unit on which to run action, e.g. "wordpress/0"
    :param action: Name of action to run.
    :param action_args: Dictionary of action parameters.
    :return str: The action UUID.

    """
    if '/' not in unit:
        raise ValueError('%s is not a unit' % unit)

    if JUJU_VERSION.major == 1:
        cmd = ['action', 'do', unit, action, '--format', 'json']
    else:
        cmd = ['run-action', unit, action, '--format', 'json']

    for key, value in (action_args or {}).items():
        cmd += ["%s=%s" % (str(key), str(value))]

    result = juju(cmd)
    action_result = json.loads(result)
    results_id = action_result["Action queued with id"]
    return results_id
action_do = run_action


def get_action_output(
        action_id, timeout=600, raise_on_timeout=False,
        full_output=False):
    """Fetch results for an action.

    If the timeout expires and the action is still not complete, an
    empty dictionary is returned. To raise an exception instead, pass
    ``raise_on_timeout=True``.

    By default, only the 'results' dictionary of the action output is
    returned. To get the full action output instead, pass
    ``full_output=True``.

    :param action_id: UUID of the action.
    :param timeout: Length of time to wait for an action to complete.
    :param raise_on_timeout: If True, :class:`amulet.helpers.TimeoutError`
        will be raised if the action is still running when the timeout
        expires.
    :param full_output: If True, returns the full output from the action.
        If False, only the 'results' dictionary from the action output is
        returned.
    :return: Action results, as json.

    """
    if JUJU_VERSION.major == 1:
        cmd = ['action', 'fetch', action_id, '--format', 'json']
    else:
        cmd = ['show-action-output', action_id, '--format', 'json']

    if timeout is not None:
        cmd += ["--wait", str(timeout)]
    raw = juju(cmd)
    result = json.loads(raw)
    status = result['status']

    if status == 'running' and raise_on_timeout:
        raise TimeoutError(
            'Action {} still running after {}s'.format(
                action_id, timeout))

    if full_output:
        return result

    if status == 'completed':
        if 'results' in result:
            return result['results']

    return {}
action_fetch = get_action_output
