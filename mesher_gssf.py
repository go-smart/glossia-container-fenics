import asyncio
import os
import math
import json
import lxml.etree 
import shutil
import logging
import yaml
from glossia.comparator.parse import gssa_xml_to_definition

logger = logging.getLogger(__name__)

_nonmeshing_groups = set(['segmented-lesions'])

def to_mesh_xml(self, gssa_root):
    definition = gssa_xml_to_definition(root)
    needles = definition.get_needles()
    regions = definition.get_regions()
    parameters = definition.get_parameters()

    root = lxml.etree.Element('gssf')
    root.set('name', 'elmer_libnuma')
    root.set('version', '1.0.2')

    # Start by creating a geometry section
    geometry = lxml.etree.Element('geometry')
    root.append(geometry)

    # We get the location of the simulation centre from the parameters
    centre_location = definition.get_parameter_value("CENTRE_LOCATION")

    # If it isn't there, then the centre will be the first needle tip, or
    # if we have been given "centroid-of-tips" instead of a set of
    # coordinates, calculate the centroid of all the tips
    if centre_location is None or centre_location == "first-needle":
        if needles:
            centre_location = definition.get_needle_parameter_value(0, "NEEDLE_TIP_LOCATION")
    elif centre_location == "centroid-of-tips":
        if needles:
            needle_tips = [definition.get_needle_parameter_value(i, "NEEDLE_TIP_LOCATION") for i in range(len(needles))]
            needle_tips = zip(*needle_tips)
            centre_location = [sum(tips) / len(needles) for tips in needle_tips]

    # If we have a needle, then use it to set the `needleaxis`
    if needles:
        needle_axis_node = lxml.etree.Element('needleaxis')

        # Get the entry and tip of the first needle
        tip_location = definition.get_needle_parameter_value(0, "NEEDLE_TIP_LOCATION")
        entry_location = definition.get_needle_parameter_value(0, "NEEDLE_ENTRY_LOCATION")
        norm = 0
        vec = []
        for c, vt, ve in zip(('x', 'y', 'z'), tip_location, entry_location):
            needle_axis_node.set(c, str(ve - vt))
            vec.append(ve - vt)
            norm += (ve - vt) * (ve - vt)
        # Based on the calculated axis, add this to the geometry
        geometry.append(needle_axis_node)

        # FIXME: is this supposed to be inside this if??
        # Use the CENTRE_OFFSET parameter to shift the geometry if required
        offset = definition.get_parameter_value("CENTRE_OFFSET")
        if offset is not None:
            for c, v in enumerate(centre_location):
                centre_location[c] = v + offset * vec[c] / math.sqrt(norm)

    # After all the calculations above, use the finally chosen centre in the
    # geometry section
    centre_location_node = lxml.etree.Element("centre")
    for c, v in zip(('x', 'y', 'z'), centre_location):
        centre_location_node.set(c, str(v))
    geometry.append(centre_location_node)

    # If we have a simulation scaling parameter, that goes into the geometry
    # section also
    if definition.get_parameter_value("SIMULATION_SCALING") is not None:
        lxml.etree.SubElement(geometry, "simulationscaling") \
            .set("ratio",
                 str(definition.get_parameter_value("SIMULATION_SCALING")))

    # Each region goes into the regions section, fairly intuitively
    region_node = lxml.etree.SubElement(root, "regions")
    for name, region in regions.items():
        regionNode = lxml.etree.SubElement(region_node, region["format"])
        regionNode.set("name", name)
        regionNode.set("input", os.path.join("input/", region["input"]))
        regionNode.set("groups", "; ".join(region["groups"]))

    # Add the parameters wholesale
    parameters = lxml.etree.SubElement(root, "constants")
    for key, parameterPair in parameters.items():
        parameter, typ = parameterPair
        parameterNode = lxml.etree.SubElement(parameters, "parameter")
        parameterNode.set("name", key)
        p = convert_parameter(parameter, typ)
        parameterNode.set("value", json.dumps(p))
        if typ is not None:
            parameterNode.set("type", typ)

    name_needle_regions = False

    # The needlelibrary needs to know if we have solid needles
    needlelibrary = lxml.etree.SubElement(root, 'needlelibrary')
    solid_needles = definition.get_parameter_value("SETTING_SOLID_NEEDLES")
    if solid_needles is not None:
        needlelibrary.set("zones", "true" if solid_needles is True else "false")
        name_needle_regions = True

    # The outer mesh, as far as we are concerned, is always CGAL
    mesher = lxml.etree.SubElement(root, "mesher")
    mesher.set('type', 'CGAL')
    # RMV: should this be reinserted?
    # if definition.get_parameter_value("SETTING_SOLID_NEEDLES") is True or definition.get_parameter_value("SETTING_ZONE_BOUNDARIES") is True:
    mesher.set("zone_boundaries", "true")

    # If we have an inner mesh, add it to the mesher
    mesher_inner = definition.get_parameter_value("SETTING_AXISYMMETRIC_INNER")
    if mesher_inner is not None:
        innerNode = lxml.etree.SubElement(mesher, "inner")
        innerNode.set("type", "axisymmetric")
        innerNode.set("template", mesher_inner)

    # Coarse inner, similarly
    mesher_inner_coarse = definition.get_parameter_value("SETTING_AXISYMMETRIC_INNER_COARSE")
    if mesher_inner_coarse is not None:
        innerNode = lxml.etree.SubElement(mesher, "inner")
        innerNode.set("type", "axisymmetric")
        innerNode.set("name", "coarse")
        innerNode.set("template", mesher_inner_coarse)

    # The extent we assume is a sphere of radius in parameters
    extent = lxml.etree.SubElement(mesher, 'extent')
    radius = definition.get_parameter_value("SIMULATION_DOMAIN_RADIUS")
    if radius is not None:
        extent.set('radius', str(radius))
    else:
        extent.set('radius', '50')

    # Adding the empty centre element tells the mesher we want a denser
    # centre than the boundaries
    lxml.etree.SubElement(mesher, 'centre')

    # Start going through the length scales
    lengthscales = lxml.etree.SubElement(mesher, 'lengthscales')

    # Two sets of fairly sensible defaults for the usual meshing case
    if definition.get_parameter_value('RESOLUTION_HIGH'):
        lengthscale_settings = [
            ('nearfield', '1.0'), ('farfield', '2.0'), ('zonefield', '1.0'),
            ('vessels', 'far')
        ]
    else:
        lengthscale_settings = [
            ('nearfield', '2.0'), ('farfield', '5.0'), ('zonefield', '2.0'),
            ('vessels', 'far')
        ]

    # Allow them to be overridden
    nearfield = definition.get_parameter_value('RESOLUTION_FIELD_NEAR')
    needlezonefield = definition.get_parameter_value('RESOLUTION_FIELD_NEEDLE_ZONE')
    if not needlezonefield:
        needlezonefield = definition.get_parameter_value('RESOLUTION_NEEDLE_ZONE_FIELD')
    farfield = definition.get_parameter_value('RESOLUTION_FIELD_FAR')
    zonefield = definition.get_parameter_value('RESOLUTION_FIELD_ZONE')

    if nearfield:
        lengthscale_settings[0] = ('nearfield', nearfield)
    if farfield:
        lengthscale_settings[1] = ('farfield', farfield)
    if zonefield:
        lengthscale_settings[2] = ('zonefield', zonefield)

    for k, v in lengthscale_settings:
        lengthscales.set(k, str(v))
    if needlezonefield:
        lengthscales.set("needlezonefield", str(needlezonefield))

    farfield = str(lengthscale_settings[1][1])
    zonefield = str(lengthscale_settings[2][1])

    # Each region may need to be added to the mesher section
    for idx, region in regions.items():
        # If we have an organ, it should appear as a zone or organ
        if region.meaning == 'organ':
            if definition.get_parameter_value('SETTING_ORGAN_AS_SUBDOMAIN'):
                zone = lxml.etree.SubElement(mesher, 'zone')
                zone.set('region', idx)
                zone.set('priority', '100')
                zone.set('characteristic_length', farfield)
            else:
                lxml.etree.SubElement(mesher, 'organ').set('region', idx)
        # If we have a zone, not excluded from meshing, then it goes in too
        elif region.format == 'zone' and not (set(region.groups) & _nonmeshing_groups):
            zone = lxml.etree.SubElement(mesher, 'zone')
            zone.set('region', idx)
            zone.set('priority', '1')
            zone.set('characteristic_length', zonefield)
        # If we have vessels, they get added also
        elif 'vessels' in region.groups or 'bronchi' in region.groups:
            # FIXME: surely this should be a surface/vessel tag?
            zone = lxml.etree.SubElement(mesher, 'zone')
            zone.set('region', idx)
            zone.set('priority', '2')
            zone.set('characteristic_length', zonefield)

    # These are standard entries
    lxml.etree.SubElement(root, 'optimizer')

    # The register of needles must be filled in
    globalNeedlesNode = lxml.etree.SubElement(root, "needles")

    if not needlezonefield:
        needlezonefield = zonefield

    # Make sure all needles are int-castable, or, if not,
    # just make up our own ordering
    try:
        needle_indices = [int(ix.replace('needle', '')) for ix in needles]
    except ValueError:
        needles  = {str(i + 1): v for i, v in enumerate(needles.values())}
        needle_indices = [int(ix) for ix in needles]
    augment = (0 in needle_indices)

    for ix, needle in needles.items():
        # Add a needle node and set the name to be our index (if we have
        # been given, say, 'needle-3' as an index, it becomes '3')
        globalNeedleNode = lxml.etree.SubElement(globalNeedlesNode, "needle")
        l = int(ix.replace('needle', ''))
        if augment:
            l += 1
        globalNeedleNode.set("name", str(l))

        # If this needle is a boundary type (the only type for the
        # moment)...
        if needle['class'] in ('solid-boundary', 'boundary'):
            # The 'file' attribute in GSSA should be a colon-separated pair
            # indicating what type of definition it is and the specifics
            # required
            location = needle['file'].split(':', 1)

            needle_mesh = None
            # If we aren't using a library type, then we need to get the
            # region
            if location[0] in ('surface', 'zone', 'both'):
                needleNode = lxml.etree.SubElement(regions, location[0])
                needleNode.set("name", str(l))
                needleNode.set("input", os.path.join("input/", location[1]))
                needleNode.set("groups", "needles")

                # TODO: surely this might be a surface?
                needle_mesh = lxml.etree.SubElement(mesher, 'zone')
                needle_mesh.set('region', str(l))
                needle_mesh.set('characteristic_length', str(needlezonefield))
                needle_mesh.set('priority', '0')
            else:
                needleNode = lxml.etree.SubElement(needlelibrary, 'needle')

                if name_needle_regions:
                    needleNode.set("name", str(l))

                # If this is a library type, set its ID
                if location[0] == 'library':
                    needleNode.set("id", location[1])
                needleNode.set("name", str(l))

                # Calculate the offset and axis for this needle
                tip_location = definition.get_needle_parameter_value(ix, "NEEDLE_TIP_LOCATION")
                entry_location = definition.get_needle_parameter_value(ix, "NEEDLE_ENTRY_LOCATION")
                needleNode.set("offset", " ".join(map(lambda c: str(c[0] - c[1]), zip(tip_location, centre_location))))
                needleNode.set("axis", " ".join(map(lambda c: str(c[0] - c[1]), zip(entry_location, tip_location))))

                # Add any needle-specific parameters
                parameter_node = lxml.etree.SubElement(globalNeedleNode, "parameters")
                for key, parameterPair in needle["parameters"].items():
                    parameter, typ = parameterPair
                    parameterNode = lxml.etree.SubElement(parameter_node, "constant")
                    parameterNode.set("name", key)
                    parameterNode.set("value", str(convert_parameter(parameter, typ)))

            # Set active region if needs be
            needle_active_length = definition.get_needle_parameter_value(ix, "NEEDLE_ACTIVE_LENGTH")
            global_active_length = definition.get_needle_parameter_value(ix, "CONSTANT_GLOBAL_ACTIVE_LENGTH")
            if needle_active_length is None:
                needle_active_length = global_active_length
            if needle_active_length is not None:
                if needle_mesh is None:
                    needle_mesh = lxml.etree.SubElement(mesher, 'zone')
                    needle_mesh.set('characteristic_length', str(needlezonefield))
                    needle_mesh.set('priority', '0')
                    needle_mesh.set('region', 'needle-' + str(l))
                activity = lxml.etree.SubElement(needle_mesh, 'activity')
                tip_location = definition.get_needle_parameter_value(ix, "NEEDLE_TIP_LOCATION")
                for c, vt, vc in zip(('x', 'y', 'z'), tip_location, centre_location):
                    activity.set(c, str(vt - vc))
                activity.set('r', str(needle_active_length))

    return root
