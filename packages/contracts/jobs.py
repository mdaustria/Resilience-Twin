"""Shared durable-job failure types."""


class LeaseBusy(Exception):
    pass


class StaleFence(Exception):
    pass
