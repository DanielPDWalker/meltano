"""Decorators for Meltano CLI commands."""

import functools

import click
from click.globals import get_current_context

from meltano.cli.utils import CliError
from meltano.core.db import project_engine
from meltano.core.project_settings_service import ProjectSettingsService


def database_uri_option(func):
    """Decorate the provided CLI function to add the `--database-uri` CLI option.

    Parameters:
        func: The function to be decorated.

    Returns:
        The decorated function.
    """

    @click.option("--database-uri", help="System database URI.")
    def decorate(*args, database_uri=None, **kwargs):
        if database_uri:
            ProjectSettingsService.config_override["database_uri"] = database_uri

        return func(*args, **kwargs)

    return functools.update_wrapper(decorate, func)


class pass_project:  # noqa: N801
    """Pass current project to decorated CLI command function."""

    __name__ = "project"

    def __init__(self, migrate=False):
        """Initialize the decorator.

        Parameters:
            migrate: Whether a silent upgrade should be performed.
        """
        self.migrate = migrate

    def __call__(self, func):
        """Decorate the given function to supply the project as its first argument.

        Parameters:
            func: The function to be decorated.

        Returns:
            The decorated function.
        """

        @database_uri_option
        def decorate(*args, **kwargs):
            ctx = get_current_context()

            project = ctx.obj["project"]
            if not project:
                raise CliError(
                    f"`{ctx.command_path}` must be run inside a Meltano project."
                    + "\nUse `meltano init <project_name>` to create one."
                )

            # register the system database connection
            engine, _ = project_engine(project, default=True)

            if self.migrate:
                from meltano.core.migration_service import MigrationService

                migration_service = MigrationService(engine)
                migration_service.upgrade(silent=True)
                migration_service.seed(project)

            func(project, *args, **kwargs)

        return functools.update_wrapper(decorate, func)
