#!/usr/bin/env python3

import sys
import asyncio
import click
import os
import shutil
import yaml

from gosmart import regions_dict

@asyncio.coroutine
def mesh_and_go(target):
    working_directory = '/shared/output/run'
    input_msh = '/shared/input/input.msh'
    labelling_yaml = '/shared/input/mesh_labelling.yml'
    regions_yaml = '/shared/input/regions.yml'

    # Launch
    task = yield from asyncio.create_subprocess_exec(
        ['go-smart-launcher', '/shared/input/settings.xml'],
        cwd=working_directory
    )

    # Hold off until meshing is complete
    yield from task.wait()

    # Pick out the relevant mesher output
    msh_input = os.path.join(working_directory, "mesher", "elmer_libnuma.msh")
    mesh_labelling_yaml = os.path.join(working_directory, "mesher", "mesh_labelling.yml")
    shutil.copyfile(msh_input, input_msh)
    shutil.copyfile(mesh_labelling_yaml, labelling_yaml)

    # Check for success from GSSF mesher-cgal
    success = (task.returncode == 0)

    # Update the regions based on this regions file
    with open(labelling_yaml, "r") as f:
        mesh_labelling = yaml.load(f)

    regions = mesh_labelling.copy()
    regions.update(regions_dict)
    for k, v in regions.items():
        if k in mesh_labelling:
            v.update(mesh_labelling[k])

    # Update the regions based on this regions file
    with open(regions_yaml, "w") as f:
        yaml.dump(regions, f, default_flow_style=False)

    # Launch
    task = yield from asyncio.create_subprocess_exec(
        ['/usr/bin/python2', target],
        cwd='/shared/output/run'
    )

    # Check for success from Python script
    success = (task.returncode == 0)

    return success


@click.command()
@click.argument('target')
def run(target):
    loop = asyncio.get_event_loop()

    future = asyncio.Future()

    asyncio.ensure_future(mesh_and_go(future, target))

    loop.run_until_complete(target)

    loop.close()

    return future.result()


if __name__ == '__main__':
    sys.exit(run())
