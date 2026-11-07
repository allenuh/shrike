from shrike.domain.queue import QueueUnavailable
from shrike.ports.queue import DispatchStore, JobPublisher


def dispatch_one(store: DispatchStore, publisher: JobPublisher) -> bool:
    claim = store.claim()
    if claim is None:
        return False
    try:
        publisher.publish(claim.envelope)
    except QueueUnavailable:
        store.failed(claim)
    else:
        store.sent(claim)
    return True
