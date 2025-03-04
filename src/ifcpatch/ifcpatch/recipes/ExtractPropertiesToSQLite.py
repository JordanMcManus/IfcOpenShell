# IfcPatch - IFC patching utiliy
# Copyright (C) 2024 Dion Moult <dion@thinkmoult.com>
#
# This file is part of IfcPatch.
#
# IfcPatch is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# IfcPatch is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with IfcPatch.  If not, see <http://www.gnu.org/licenses/>.


import os
import re
import json
import time
import tempfile
import ifcopenshell

try:
    import sqlite3
except:
    print("No SQLite support")


class Patcher:
    def __init__(
        self,
        src,
        file,
        logger,
    ):
        """Extracts properties and relationships from a IFC-SPF model to SQLite.

        This is a lossy extraction which simplifies popular properties to key
        value pairs.

        Example:

        .. code:: python

            result = ifcpatch.execute({"input": fn, "file": model, "recipe": "ExtractPropertiesToSQLite"})
            ifcpatch.write(result, "output.sqlite")
        """
        self.src = src
        self.file = file
        self.logger = logger

    def patch(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        db_file = tmp.name
        self.db = sqlite3.connect(db_file)
        self.c = self.db.cursor()
        self.file_patched = db_file

        self.c.execute(
            """
            CREATE TABLE IF NOT EXISTS elements (
                id integer PRIMARY KEY NOT NULL UNIQUE,
                global_id text,
                ifc_class text,
                predefined_type text,
                name text,
                description text
            );
        """
        )
        self.c.execute("CREATE INDEX IF NOT EXISTS idx_global_id ON elements (global_id);")
        self.c.execute("CREATE INDEX IF NOT EXISTS idx_ifc_class ON elements (ifc_class);")
        self.c.execute("CREATE INDEX IF NOT EXISTS idx_predefined_type ON elements (predefined_type);")

        self.c.execute(
            """
            CREATE TABLE IF NOT EXISTS relationships (
                from_id integer NOT NULL,
                type text,
                to_id integer NOT NULL
            );
        """
        )
        self.c.execute("CREATE INDEX IF NOT EXISTS idx_from_id ON relationships (from_id);")

        self.c.execute(
            """
           CREATE TABLE IF NOT EXISTS properties (
               element_id integer NOT NULL,
               set_name text,
               name text,
               value text
           );
        """
        )
        self.c.execute("CREATE INDEX IF NOT EXISTS idx_element_id ON properties (element_id);")

        elements = self.file.by_type("IfcObjectDefinition")

        rows = []
        properties = []
        relationships = []
        id_map = {e.id(): i for i, e in enumerate(elements)}
        for i, element in enumerate(elements):
            rows.append([
                i,
                element[0],
                element.is_a(),
                ifcopenshell.util.element.get_predefined_type(element),
                element[2],
                element[3],
            ])
            psets = ifcopenshell.util.element.get_psets(element, should_inherit=False)
            for pset_name, pset_data in psets.items():
                for prop_name, value in pset_data.items():
                    if prop_name == "id" or value is None or value == "":
                        continue
                    if isinstance(value, bool):
                        value = "True" if value else "False"
                    elif not isinstance(value, str):
                        value = str(value)
                    properties.append([i, pset_name, prop_name, value])
            relating_type = ifcopenshell.util.element.get_type(element)
            if relating_type and relating_type != element:
                relationships.append([i, "IfcRelDefinesByType", id_map[relating_type.id()]])

        self.c.executemany("INSERT INTO elements VALUES (?, ?, ?, ?, ?, ?);", rows)
        self.c.executemany("INSERT INTO properties VALUES (?, ?, ?, ?);", properties)
        self.c.executemany("INSERT INTO relationships VALUES (?, ?, ?);", relationships)

        self.db.commit()
        self.db.close()
