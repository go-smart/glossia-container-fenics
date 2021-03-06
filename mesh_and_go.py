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
import traceback
import lxml.etree
import mesher_gssf

import gosmart
gosmart.setup(False)


@asyncio.coroutine
def mesh_and_go(target, mesh=None, gssf_settings_xml='/shared/input/settings.xml'):
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
            gssf_settings_xml,
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
@click.option('--gssa-xml', default=None)
@click.argument('target')
def run(mesh, gssa_xml, target):
    print("Starting Mesh & Go...")

    gssf_settings_xml = '/shared/input/settings.xml'

    if gssa_xml:
        if not os.path.exists(gssa_xml):
            raise RuntimeError("Passed GSSA-XML file does not exist")

        with open(gssa_xml, 'r') as f:
            tree = lxml.etree.parse(f)

        gssf_xml_root = mesher_gssf.to_mesh_xml(tree.getroot())

        gssf_settings_xml = '/shared/output/settings.xml'
        with open(gssf_settings_xml, 'w') as f:
            f.write(lxml.etree.tostring(gssf_xml_root, pretty_print=True).decode('utf-8'))

    loop = asyncio.get_event_loop()

    future = asyncio.ensure_future(mesh_and_go(target, mesh, gssf_settings_xml))

    try:
        loop.run_until_complete(future)
    except:
        traceback.print_exc()
        result = 1
    else:
        result = future.result()
    finally:
        loop.close()

    print("Exiting Mesh & Go with code %d" % int(result))

    if result != 0:
        raise SystemExit(result)

    return 0


if __name__ == '__main__':
    sys.exit(run())
