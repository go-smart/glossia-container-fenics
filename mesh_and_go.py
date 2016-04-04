#!/usr/bin/env python3
"""Tool to automatically perform volumetric meshing prior to
executing a Glossia Python Container Module simulation. Updates
region YAML files to note mesh labels for specific regions."""

import sys
import asyncio
import click
import os
import shutil
import yaml

import gosmart
gosmart.setup(False)


@asyncio.coroutine
def mesh_and_go(target, mesh=None):
    working_directory = '/shared/output/run'
    original_input = '/shared/input'
    run_input = os.path.join(working_directory, 'input')
    input_msh = os.path.join(run_input, 'input.msh')
    labelling_yaml = os.path.join(run_input, 'mesh_labelling.yml')
    original_regions_yaml = os.path.join(original_input, 'regions.yml')
    regions_yaml = os.path.join(run_input, 'regions.yml')

    try:
        shutil.rmtree(run_input)
    except FileNotFoundError:
        pass

    shutil.copytree(original_input, run_input)

    if mesh is None:
        # Launch
        task = yield from asyncio.create_subprocess_exec(
            'go-smart-launcher',
            '/shared/input/settings.xml',
            cwd=working_directory
        )

        # Hold off until meshing is complete
        yield from task.wait()

        # Pick out the relevant mesher output
        msh_input = os.path.join(
            working_directory,
            "mesher",
            "elmer_libnuma.msh"
        )

        mesh_labelling_yaml = os.path.join(
            working_directory,
            "mesher",
            "mesh_labelling.yml"
        )

        # Check for success from GSSF mesher-cgal
        success = (task.returncode == 0)

        if not success:
            return task.returncode
    else:
        msh_input, mesh_labelling_yaml = mesh.split(':')

    shutil.copyfile(msh_input, input_msh)
    shutil.copyfile(mesh_labelling_yaml, labelling_yaml)

    # Update the regions based on this regions file
    with open(labelling_yaml, "r") as f:
        mesh_labelling = yaml.load(f)

    regions = mesh_labelling.copy()
    with open(original_regions_yaml, "r") as f:
        region_dict = yaml.load(f)
    regions.update(region_dict)

    for k, v in regions.items():
        if k in mesh_labelling:
            v.update(mesh_labelling[k])

    # Update the regions based on this regions file
    with open(regions_yaml, "w") as f:
        yaml.dump(regions, f, default_flow_style=False)

    # Launch
    print("Running target", target)
    task = yield from asyncio.create_subprocess_exec(
        '/usr/bin/python2',
        target,
        stdout=sys.stdout,
        stderr=sys.stderr,
        cwd=working_directory
    )

    yield from task.wait()

    print("Target run")

    return task.returncode


@click.command()
@click.option('--mesh', default=None,
              help='Colon separated mesh filename and labelling filename')
@click.argument('target')
def run(mesh, target):
    loop = asyncio.get_event_loop()

    future = asyncio.ensure_future(mesh_and_go(target, mesh))

    loop.run_until_complete(future)

    loop.close()

    return future.result()


if __name__ == '__main__':
    exit_code = run()
    print("Exiting with code %d" % int(exit_code))
    sys.exit(exit_code)
