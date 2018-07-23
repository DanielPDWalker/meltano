import click
import importlib
import sys
import logging
import functools

from meltano.common.service import MeltanoService
from meltano.common.manifest_reader import ManifestReader
from meltano.common.manifest_writer import ManifestWriter
from meltano.common.manifest import Manifest
from meltano.common.db import DB
from meltano.common.utils import setup_db, pop_all
from meltano.schema import schema_apply
from meltano.stream import MeltanoStream


service = MeltanoService()
# print(service.auto_discover())


def build_extractor(name):
    # this should register the module
    try:
        importlib.import_module("meltano.extract.{}".format(name))
    except ImportError as e:
        logging.error("Cannot find the extractor {0}, you might need to install it (meltano-extract-{0})".format(name))

    schema = None
    stream = MeltanoStream(sys.stdout.fileno())
    extractor = service.create_extractor("com.meltano.extract.{}".format(name), stream.create_writer())
    return extractor


def build_loader(name):
    # this should register the module
    try:
        importlib.import_module("meltano.load.{}".format(name))
    except ImportError as e:
        logging.error("Cannot find the loader {0}, you might need to install it (meltano-load-{0})".format(name))

    schema = None
    stream = MeltanoStream(sys.stdin.fileno())
    loader = service.create_loader("com.meltano.load.{}".format(name), stream.create_reader())
    return loader


def build_manifest(source, manifest_path):
    with open(manifest_path, 'r') as file:
        return ManifestReader(source).load(file)


def register_manifest(manifest):
    for id in service.register_manifest(manifest):
        logging.debug("Registered entity {}".format(id))


def db_options(func):
    @click.option('-S', '--schema',
                  required=True)

    @click.option('-H', '--host',
                  envvar='PG_ADDRESS',
                  default='localhost',
                  help="Database schema to use.")

    @click.option('-p', '--port',
                  type=int,
                  envvar='PG_PORT',
                  default=5432)

    @click.option('-d', '-db', 'database',
                  envvar='PG_DATABASE',
                  default=lambda: os.getenv('USER', ''),
                  help="Database to import the data to.")

    @click.option('-T', '--table', 'table_name',
                  help="Table to import the data to.")

    @click.option('-u', '--user',
                  envvar='PG_USERNAME',
                  default=lambda: os.getenv('USER', ''),
                  help="Specifies the user to connect to the database with.")
    @click.password_option(envvar='PG_PASSWORD')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import pdb; pdb.set_trace()
        config = pop_all(("schema", "host", "port", "database", "table_name", "user", "password"), kwargs)
        DB.setup(**config)
        return func(*args, **kwargs)
    return wrapper


@click.group()
def root():
    pass


@root.command()
@click.argument('manifest')
def describe(manifest):
    manifest = build_manifest('describe', manifest)
    print(manifest)


@root.command()
@click.argument('extractor')
@click.argument('output')
def discover(extractor, output):
    manifest = Manifest(extractor,
                        entities=extractor.discover_entities())

    extractor = build_extractor(extractor)

    with open(output + ".yaml", 'w') as out:
        writer = ManifestWriter(out)
        writer.write(manifest)


@root.command()
@click.argument('extractor')
@click.argument('manifest')
def extract(extractor, manifest):
    source, _ = manifest.split(".")

    register_manifest(build_manifest(source, manifest))
    extractor = build_extractor(extractor)

    logging.info("Extracting data...")
    extractor.run()
    logging.info("Extraction complete.")


@root.command()
@click.argument('loader')
@click.argument('manifest')
def load(loader, manifest):
    source, _ = manifest.split(".")

    register_manifest(build_manifest(source, manifest))
    loader = build_loader(loader)

    logging.info("Waiting for data...")
    loader.run()
    logging.info("Integration complete.")


@root.command()
@db_options
@click.argument('manifest')
def apply_schema(manifest):
    source, _ = manifest.split(".")
    manifest = build_manifest(source, manifest)

    with DB.open() as db:
        schema_apply(db, manifest.as_schema())


def main():
    logging.basicConfig(level=logging.DEBUG)
    root()
