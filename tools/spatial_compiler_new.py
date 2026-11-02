    def vlm_patch_to_ops(self, patch_payload: dict) -> list:
        """Convert VLM patch JSON to WGSL PatchOp structures"""
        ops = []

        for patch in patch_payload.get("patches", []):
            patch_type = patch.get("type", "").upper()
            target = patch.get("target", "")
            color = patch.get("color", [236, 80, 80])  # Default LDI color

            # Handle combined types (e.g., "COMPACTION|REALLOCATION|COALESCING")
            # Pick the first matching operation
            ops_to_try = patch_type.split("|")
            processed = False

            for op_to_check in ops_to_try:
                op_to_check = op_to_check.strip()
                if processed:
                    break

                if "WRITE_PIXEL" in op_to_check or op_to_check == "WRITE_PIXEL":
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_WRITE_PIXEL,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": color[0],
                            "g": color[1],
                            "b": color[2],
                        })
                        processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse WRITE_PIXEL patch: {e}")

                elif "FILL_RECT" in op_to_check or op_to_check == "FILL_RECT":
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_FILL_RECT,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": color[0],
                            "g": color[1],
                            "b": color[2],
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse FILL_RECT patch: {e}")

                elif "CLEAR_REGION" in op_to_check or op_to_check == "CLEAR_REGION":
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_CLEAR_REGION,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse CLEAR_REGION patch: {e}")

                elif "COMPACTION" in op_to_check or op_to_check == "COMPACTION":
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_FILL_RECT,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": 236,  # LDI red
                            "g": 80,   # LDI green
                            "b": 80,   # LDI blue
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse COMPACTION patch: {e}")

                elif "REALLOCATION" in op_to_check or op_to_check == "REALLOCATION":
                    try:
                        if " to " in target:
                            parts = target.split(" to ")
                            src_coords = self._parse_coordinate(parts[0].replace("from ", ""))
                            dest_coords = self._parse_coordinate(parts[1])

                            ops.append({
                                "op_type": OP_COPY_BLOCK,
                                "x": dest_coords[0],
                                "y": dest_coords[1],
                                "z": dest_coords[2],
                                "width": 4,
                                "height": 4,
                                "src_x": src_coords[0],
                                "src_y": src_coords[1],
                                "src_z": src_coords[2],
                            })
                            processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse REALLOCATION patch: {e}")

                elif "COALESCING" in op_to_check or op_to_check == "COALESCING":
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_CLEAR_REGION,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError as e:
                        print(f"WARNING: Failed to parse COALESCING patch: {e}")

        return ops