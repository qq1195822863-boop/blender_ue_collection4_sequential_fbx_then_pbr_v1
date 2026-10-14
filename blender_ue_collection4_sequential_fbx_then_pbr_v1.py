import bpy
import os
import traceback

# ============================================================
# Blender -> UE Collection 4 Sequential Asset Pipeline V1
#
# PHASE 1:
#   原始 FBX/UCX 脚本完整执行
#   Collection 4 -> 每个 Mesh -> FBX + UCX
#
# PHASE 2:
#   仅在 PHASE 1 全部资产成功后执行
#   原始 PBR 脚本的 Material Slot / Node Tree / PBR 提取逻辑
#   输出到对应 Mesh 文件夹下的 Texture 目录
#
# 最终：
#
# collection4/
# ├─ SM_xxx/
# │  ├─ SM_xxx.fbx
# │  └─ Texture/
# │     ├─ M_xxx/
# │     │  ├─ T_xxx_D.png
# │     │  └─ T_xxx_N.png
# │     └─ M_xxx_02/
# │        └─ ...
# └─ Collection_Export_Controller_Log.txt
#
# 两套原始脚本的功能代码通过独立命名空间执行，避免
# get_collection / sanitize_* / Main 等同名函数互相覆盖。
# ============================================================

COLLECTION_NAME = "Collection 4"
EXPORT_ROOT = r"C:\Users\Administrator\Desktop\元神\广西\fbx\collection4"

# 严格按你的要求：
# 第一阶段全部 Mesh/FBX/UCX 都完成后，第二阶段才开始。
# 只要第一阶段存在失败项，就停止，不进入 PBR 阶段。
REQUIRE_ALL_FBX_SUCCESS_BEFORE_PBR = True

# 第二阶段贴图根目录名
TEXTURE_ROOT_NAME = "Texture"

# ============================================================
# Embedded original scripts
# ============================================================

FBX_SOURCE = 'import bpy\nimport os\nimport re\nimport bmesh\nfrom mathutils import Vector\n\n# ============================================================\n# Blender -> UE FBX 自动导出 V0.12\n# Collection 5 / Render Mesh + 精细多凸包 UCX\n#\n# V0.6 的 Z 分层会把整个楼梯外轮廓拉成“大盒子”。\n# V0.12 改为：\n#\n#   Render Mesh\n#       ↓\n#   按真实三角面空间位置递归分块\n#       ↓\n#   每个局部块独立 Convex Hull\n#       ↓\n#   多个 UCX 拼成宏观轮廓\n#\n# 这样不会再用“整个模型一个包围盒”。\n#\n# 目标：\n#   - 保持模型整体长宽高\n#   - 跟随楼梯/台阶/侧墙等宏观轮廓\n#   - 不追踪雕刻、碎石等微小细节\n#   - 每个 UCX 都是独立凸体\n#   - UE 可通过 Import Collision 自动识别\n#\n# 注意：\n# UE 的 UCX 本质上要求“凸碰撞体”。\n# 因此复杂凹形模型不可能由一个 UCX 完美表达。\n# V0.7 使用多个局部凸包逼近真实外轮廓。\n# ============================================================\n\nCOLLECTION_NAME = "Collection 4"\nEXPORT_ROOT = r"C:\\Users\\Administrator\\Desktop\\元神\\广西\\fbx\\collection_4"\n\n# ============================================================\n# Collision Quality\n# ============================================================\n\n# 最大 UCX 数量。\n# 仅小幅增加上限，避免转角区域被合并。\n# 其它区域算法保持不变。\nMAX_HULLS = 24\n\n# 每个局部 Hull 最大三角面数。\n# V0.12 从 80 小幅降到 50，只提高局部转角分辨率。\n# 越小越贴合，Hull 越多。\nTARGET_TRIANGLES_PER_HULL = 999999\n\n# 单个局部块最少三角面\nMIN_TRIANGLES_PER_HULL = 12\n\n# 递归最大深度\nMAX_DEPTH = 10\n\n# 删除旧自动 UCX 后重新生成\nREBUILD_COLLISION = True\n\n# Blender 视口是否显示 UCX\nSHOW_GENERATED_COLLISION = True\n\n# ============================================================\n# FBX：严格保持之前已经验证的参数\n# ============================================================\n\nFBX_SETTINGS = {\n    "use_selection": True,\n    "use_visible": False,\n    "use_active_collection": False,\n    "object_types": {\'MESH\'},\n\n    "global_scale": 1.0,\n    "apply_scale_options": \'FBX_SCALE_NONE\',\n    "axis_forward": \'-Y\',\n    "axis_up": \'Z\',\n    "apply_unit_scale": False,\n    "use_space_transform": False,\n    "bake_space_transform": False,\n\n    "mesh_smooth_type": \'FACE\',\n    "use_subsurf": False,\n    "use_mesh_modifiers": False,\n    "use_mesh_edges": False,\n    "use_tspace": False,\n\n    "bake_anim": False,\n    "add_leaf_bones": False,\n    "use_custom_props": False,\n}\n\n\n# ============================================================\n# Name\n# ============================================================\n\ndef sanitize_asset_name(name):\n\n    match = re.match(r"^(.*)\\.(\\d{3})$", name)\n\n    if match:\n        base = match.group(1)\n        number = int(match.group(2))\n        name = f"{base}_{number:02d}"\n\n    name = re.sub(r\'[\\\\/:*?"<>|]\', \'_\', name)\n    name = re.sub(r\'\\s+\', \'_\', name)\n    name = re.sub(r\'_+\', \'_\', name)\n    name = name.strip(\'_\')\n\n    if not name.startswith("SM_"):\n        name = "SM_" + name\n\n    return name\n\n\n# ============================================================\n# Collection / Mesh\n# ============================================================\n\ndef get_collection():\n\n    collection = bpy.data.collections.get(\n        COLLECTION_NAME\n    )\n\n    if collection is None:\n        raise RuntimeError(\n            f"找不到 Collection：{COLLECTION_NAME}"\n        )\n\n    return collection\n\n\ndef get_render_meshes(collection):\n\n    meshes = [\n        obj\n        for obj in collection.objects\n        if obj.type == \'MESH\'\n        and not obj.name.upper().startswith("UCX_")\n    ]\n\n    if not meshes:\n        raise RuntimeError(\n            f"Collection \'{COLLECTION_NAME}\' 中没有找到 Render Mesh。"\n        )\n\n    return meshes\n\n\n# ============================================================\n# Selection\n# ============================================================\n\ndef select_only(obj):\n\n    bpy.ops.object.select_all(\n        action=\'DESELECT\'\n    )\n\n    obj.select_set(True)\n\n    bpy.context.view_layer.objects.active = obj\n\n\ndef select_objects(objects):\n\n    bpy.ops.object.select_all(\n        action=\'DESELECT\'\n    )\n\n    for obj in objects:\n        obj.select_set(True)\n\n    if objects:\n        bpy.context.view_layer.objects.active = objects[0]\n\n\n# ============================================================\n# Transform\n# ============================================================\n\ndef apply_rotation_scale(obj):\n\n    select_only(obj)\n\n    bpy.ops.object.transform_apply(\n        location=False,\n        rotation=True,\n        scale=True\n    )\n\n\ndef get_bbox(obj):\n\n    points = [\n        Vector(v)\n        for v in obj.bound_box\n    ]\n\n    min_v = Vector((\n        min(p.x for p in points),\n        min(p.y for p in points),\n        min(p.z for p in points)\n    ))\n\n    max_v = Vector((\n        max(p.x for p in points),\n        max(p.y for p in points),\n        max(p.z for p in points)\n    ))\n\n    return min_v, max_v\n\n\ndef center_geometry(obj):\n\n    min_v, max_v = get_bbox(obj)\n\n    center = (min_v + max_v) * 0.5\n\n    for vertex in obj.data.vertices:\n        vertex.co -= center\n\n    obj.data.update()\n\n    return center\n\n\ndef normalize_transform(obj):\n\n    obj.location = (\n        0.0,\n        0.0,\n        0.0\n    )\n\n    obj.rotation_euler = (\n        0.0,\n        0.0,\n        0.0\n    )\n\n    obj.scale = (\n        1.0,\n        1.0,\n        1.0\n    )\n\n    bpy.context.view_layer.update()\n\n\n# ============================================================\n# Remove old UCX\n# ============================================================\n\ndef remove_old_ucx(clean_name):\n\n    prefix = f"UCX_{clean_name}_"\n\n    old_objects = [\n        obj\n        for obj in list(bpy.data.objects)\n        if obj.type == \'MESH\'\n        and obj.name.startswith(prefix)\n    ]\n\n    for obj in old_objects:\n\n        mesh = obj.data\n\n        bpy.data.objects.remove(\n            obj,\n            do_unlink=True\n        )\n\n        if mesh and mesh.users == 0:\n            bpy.data.meshes.remove(mesh)\n\n    return len(old_objects)\n\n\n# ============================================================\n# Triangle Data\n# ============================================================\n\ndef build_triangle_data(obj):\n\n    vertices = [\n        v.co.copy()\n        for v in obj.data.vertices\n    ]\n\n    triangles = []\n\n    for poly in obj.data.polygons:\n\n        if len(poly.vertices) < 3:\n            continue\n\n        # Blender Mesh Polygon 通常已经是三角化后的索引，\n        # 但这里对 N-gon 做 fan triangulation。\n        ids = list(poly.vertices)\n\n        if len(ids) == 3:\n\n            a, b, c = ids\n\n            center = (\n                vertices[a]\n                + vertices[b]\n                + vertices[c]\n            ) / 3.0\n\n            triangles.append(\n                (a, b, c, center)\n            )\n\n        else:\n\n            root = ids[0]\n\n            for i in range(\n                1,\n                len(ids) - 1\n            ):\n\n                a = root\n                b = ids[i]\n                c = ids[i + 1]\n\n                center = (\n                    vertices[a]\n                    + vertices[b]\n                    + vertices[c]\n                ) / 3.0\n\n                triangles.append(\n                    (a, b, c, center)\n                )\n\n    return vertices, triangles\n\n\n# ============================================================\n# Spatial Recursive Partition\n# ============================================================\n\n\ndef cluster_bounds(triangle_ids, triangles):\n    centers = [\n        triangles[i][3]\n        for i in triangle_ids\n    ]\n\n    min_v = Vector((\n        min(p.x for p in centers),\n        min(p.y for p in centers),\n        min(p.z for p in centers)\n    ))\n\n    max_v = Vector((\n        max(p.x for p in centers),\n        max(p.y for p in centers),\n        max(p.z for p in centers)\n    ))\n\n    return min_v, max_v\n\n\ndef cluster_points(triangle_ids, triangles, vertices):\n    """\n    从当前三角面簇中提取真实 Mesh 顶点。\n    """\n    vertex_ids = set()\n\n    for tri_id in triangle_ids:\n        a, b, c, _ = triangles[tri_id]\n        vertex_ids.add(a)\n        vertex_ids.add(b)\n        vertex_ids.add(c)\n\n    return [vertices[i] for i in vertex_ids]\n\n\ndef convex_hull_volume(points):\n    """\n    只用于“候选切分评估”，不创建最终对象。\n\n    通过 BMesh Convex Hull 得到候选区域的凸包体积。\n    体积越大，说明这个区域越可能包含被凸包填充的空白空间。\n    """\n    if len(points) < 4:\n        return 0.0\n\n    # 去重\n    unique = {}\n    for p in points:\n        unique[\n            (\n                round(p.x, 6),\n                round(p.y, 6),\n                round(p.z, 6)\n            )\n        ] = p\n\n    points = list(unique.values())\n\n    if len(points) < 4:\n        return 0.0\n\n    bm = bmesh.new()\n\n    try:\n        for p in points:\n            bm.verts.new(p)\n\n        bm.verts.ensure_lookup_table()\n\n        result = bmesh.ops.convex_hull(\n            bm,\n            input=list(bm.verts),\n            use_existing_faces=False\n        )\n\n        hull_verts = [\n            v for v in result.get("geom", [])\n            if isinstance(v, bmesh.types.BMVert)\n        ]\n\n        hull_faces = [\n            f for f in result.get("geom", [])\n            if isinstance(f, bmesh.types.BMFace)\n        ]\n\n        if len(hull_verts) < 4 or len(hull_faces) < 4:\n            return 0.0\n\n        # 凸包面三角化后计算体积\n        volume = 0.0\n\n        for face in hull_faces:\n            vs = list(face.verts)\n\n            if len(vs) < 3:\n                continue\n\n            p0 = vs[0].co\n\n            for i in range(1, len(vs) - 1):\n                p1 = vs[i].co\n                p2 = vs[i + 1].co\n\n                volume += (\n                    p0.dot(\n                        p1.cross(p2)\n                    )\n                ) / 6.0\n\n        return abs(volume)\n\n    finally:\n        bm.free()\n\n\ndef find_candidate_cuts(\n    triangle_ids,\n    triangles\n):\n    """\n    不再简单“取中位数”。\n\n    同时测试：\n    - X/Y/Z 三轴\n    - 25/40/50/60/75% 分位点\n    - 真实三角形中心的最大空间间隙\n\n    这样楼梯台阶、侧墙、扶手的宏观体积会更容易\n    在几何自然断点处分离。\n    """\n\n    if len(triangle_ids) < MIN_TRIANGLES_PER_HULL * 2:\n        return []\n\n    candidates = []\n\n    for axis in range(3):\n\n        ordered = sorted(\n            triangle_ids,\n            key=lambda idx: triangles[idx][3][axis]\n        )\n\n        values = [\n            triangles[idx][3][axis]\n            for idx in ordered\n        ]\n\n        if len(values) < 2:\n            continue\n\n        # 分位点\n        fractions = (\n            0.25,\n            0.40,\n            0.50,\n            0.60,\n            0.75\n        )\n\n        for fraction in fractions:\n\n            cut_index = int(\n                len(ordered) * fraction\n            )\n\n            if cut_index <= 0:\n                continue\n\n            if cut_index >= len(ordered):\n                continue\n\n            left = ordered[:cut_index]\n            right = ordered[cut_index:]\n\n            if (\n                len(left) < MIN_TRIANGLES_PER_HULL\n                or len(right) < MIN_TRIANGLES_PER_HULL\n            ):\n                continue\n\n            cut_value = (\n                values[cut_index - 1]\n                + values[cut_index]\n            ) * 0.5\n\n            candidates.append(\n                (\n                    axis,\n                    cut_value,\n                    left,\n                    right\n                )\n            )\n\n        # 最大空间间隙\n        max_gap = 0.0\n        max_gap_index = -1\n\n        for i in range(1, len(values)):\n\n            gap = values[i] - values[i - 1]\n\n            if gap > max_gap:\n                max_gap = gap\n                max_gap_index = i\n\n        extent = values[-1] - values[0]\n\n        if (\n            max_gap_index > 0\n            and max_gap_index < len(values)\n            and extent > 1e-6\n            and max_gap / extent > 0.025\n        ):\n\n            left = ordered[:max_gap_index]\n            right = ordered[max_gap_index:]\n\n            if (\n                len(left) >= MIN_TRIANGLES_PER_HULL\n                and len(right) >= MIN_TRIANGLES_PER_HULL\n            ):\n\n                cut_value = (\n                    values[max_gap_index - 1]\n                    + values[max_gap_index]\n                ) * 0.5\n\n                candidates.append(\n                    (\n                        axis,\n                        cut_value,\n                        left,\n                        right\n                    )\n                )\n\n    return candidates\n\n\ndef evaluate_split(\n    left,\n    right,\n    parent_volume,\n    triangles,\n    vertices\n):\n    """\n    核心判定：\n\n        parent convex volume\n                    ↓\n        child A + child B convex volume\n\n    如果切开后总凸包体积明显下降，\n    说明原来的一个 Hull 确实在“填空”。\n\n    这种切法优先。\n    """\n\n    left_points = cluster_points(\n        left,\n        triangles,\n        vertices\n    )\n\n    right_points = cluster_points(\n        right,\n        triangles,\n        vertices\n    )\n\n    if (\n        len(left_points) < 4\n        or len(right_points) < 4\n    ):\n        return None\n\n    left_volume = convex_hull_volume(\n        left_points\n    )\n\n    right_volume = convex_hull_volume(\n        right_points\n    )\n\n    child_volume = (\n        left_volume\n        + right_volume\n    )\n\n    if parent_volume <= 1e-9:\n        return None\n\n    saving = (\n        parent_volume\n        - child_volume\n    )\n\n    saving_ratio = (\n        saving\n        / parent_volume\n    )\n\n    # 过于极端的不平衡切分不优先\n    balance = min(\n        len(left),\n        len(right)\n    ) / max(\n        len(left),\n        len(right)\n    )\n\n    # 综合评分：\n    # 体积节省是第一权重，\n    # 平衡性作为轻微奖励。\n    score = (\n        saving_ratio\n        * (\n            0.75\n            + 0.25 * balance\n        )\n    )\n\n    return {\n        "left": left,\n        "right": right,\n        "left_volume": left_volume,\n        "right_volume": right_volume,\n        "saving_ratio": saving_ratio,\n        "balance": balance,\n        "score": score\n    }\n\n\ndef find_best_split(\n    cluster,\n    triangles,\n    vertices\n):\n    """\n    对一个 Cluster 找最有效的切分。\n\n    不再按“最长轴 + 中位数”机械切。\n    """\n    if len(cluster) < MIN_TRIANGLES_PER_HULL * 2:\n        return None\n\n    points = cluster_points(\n        cluster,\n        triangles,\n        vertices\n    )\n\n    parent_volume = convex_hull_volume(\n        points\n    )\n\n    if parent_volume <= 1e-9:\n        return None\n\n    candidates = find_candidate_cuts(\n        cluster,\n        triangles\n    )\n\n    best = None\n\n    for axis, cut_value, left, right in candidates:\n\n        result = evaluate_split(\n            left,\n            right,\n            parent_volume,\n            triangles,\n            vertices\n        )\n\n        if result is None:\n            continue\n\n        result["axis"] = axis\n        result["cut_value"] = cut_value\n\n        if (\n            best is None\n            or result["score"] > best["score"]\n        ):\n            best = result\n\n    # 只有真正能减少明显空包体积时才切\n    if (\n        best is None\n        or best["saving_ratio"] < 0.08\n    ):\n        return None\n\n    return best\n\n\ndef build_connected_components(triangles):\n    """\n    先识别真正相连的几何组件。\n\n    楼梯主体 / 扶手 / 装饰，如果本身就是\n    不相连的 Mesh 几何，这一步会天然隔离。\n    """\n\n    vertex_to_triangles = {}\n\n    for tri_id, tri in enumerate(triangles):\n\n        a, b, c, _ = tri\n\n        for vid in (a, b, c):\n\n            vertex_to_triangles.setdefault(\n                vid,\n                []\n            ).append(tri_id)\n\n    adjacency = [\n        set()\n        for _ in triangles\n    ]\n\n    for ids in vertex_to_triangles.values():\n\n        if len(ids) < 2:\n            continue\n\n        for i in range(len(ids)):\n\n            for j in range(\n                i + 1,\n                len(ids)\n            ):\n\n                a = ids[i]\n                b = ids[j]\n\n                adjacency[a].add(b)\n                adjacency[b].add(a)\n\n    visited = set()\n    components = []\n\n    for start in range(len(triangles)):\n\n        if start in visited:\n            continue\n\n        stack = [start]\n        visited.add(start)\n\n        component = []\n\n        while stack:\n\n            current = stack.pop()\n            component.append(current)\n\n            for neighbor in adjacency[current]:\n\n                if neighbor in visited:\n                    continue\n\n                visited.add(neighbor)\n                stack.append(neighbor)\n\n        components.append(component)\n\n    return components\n\n\ndef build_spatial_clusters(\n    triangles,\n    vertices\n):\n    """\n    V0.12 核心：\n\n    ① 先按真实拓扑组件分离\n    ② 每个组件计算自己的凸包体积\n    ③ 每次寻找“最浪费体积”的 Cluster\n    ④ 在 X/Y/Z 多个候选位置试切\n    ⑤ 只有当切分明显减少空白体积时才继续\n    ⑥ 不设死的低数量上限，只在确实有收益时继续\n\n    结果倾向于：\n        楼梯主体 -> 少量大 Hull\n        转角/侧墙 -> 独立 Hull\n        扶手 -> 独立 Hull\n        不会为了数量强行把结构揉在一起\n    """\n\n    components = build_connected_components(\n        triangles\n    )\n\n    # 极小组件直接保留，但后续会根据空间关系\n    # 尽量与最近的大组件合并。\n    components.sort(\n        key=len,\n        reverse=True\n    )\n\n    clusters = []\n\n    # 先放入每个真实组件\n    for component in components:\n        clusters.append(component)\n\n    # 迭代细分，最多 24 个。\n    # 用户要求“最好少点”，因此设置软阈值：\n    # 如果已经达到 12 个且后续切分收益很小，就停止。\n    HARD_MAX_HULLS = 24\n    SOFT_TARGET_HULLS = 12\n\n    while len(clusters) < HARD_MAX_HULLS:\n\n        best_cluster_index = -1\n        best_split = None\n\n        for i, cluster in enumerate(clusters):\n\n            split = find_best_split(\n                cluster,\n                triangles,\n                vertices\n            )\n\n            if split is None:\n                continue\n\n            if (\n                best_split is None\n                or split["score"]\n                > best_split["score"]\n            ):\n\n                best_cluster_index = i\n                best_split = split\n\n        if best_split is None:\n            break\n\n        # 达到软目标后，只接受非常明显的收益。\n        if len(clusters) >= SOFT_TARGET_HULLS:\n\n            if best_split["saving_ratio"] < 0.18:\n                break\n\n        target = clusters[\n            best_cluster_index\n        ]\n\n        clusters.pop(\n            best_cluster_index\n        )\n\n        clusters.append(\n            best_split["left"]\n        )\n\n        clusters.append(\n            best_split["right"]\n        )\n\n    return clusters\n\n\n# ============================================================\n# Convex Hull\n# ============================================================\n\ndef create_convex_hull_mesh(\n    points,\n    name\n):\n\n    # 去重\n    unique = {}\n\n    for p in points:\n\n        key = (\n            round(p.x, 6),\n            round(p.y, 6),\n            round(p.z, 6)\n        )\n\n        unique[key] = p\n\n    points = list(\n        unique.values()\n    )\n\n    if len(points) < 4:\n        return None\n\n    bm = bmesh.new()\n\n    try:\n\n        bm_verts = [\n            bm.verts.new(p)\n            for p in points\n        ]\n\n        bm.verts.ensure_lookup_table()\n\n        result = bmesh.ops.convex_hull(\n            bm,\n            input=bm_verts,\n            use_existing_faces=False\n        )\n\n        hull_geom = result.get(\n            "geom",\n            []\n        )\n\n        hull_verts = [\n            v\n            for v in hull_geom\n            if isinstance(\n                v,\n                bmesh.types.BMVert\n            )\n        ]\n\n        hull_faces = [\n            f\n            for f in hull_geom\n            if isinstance(\n                f,\n                bmesh.types.BMFace\n            )\n        ]\n\n        if len(hull_verts) < 4:\n            return None\n\n        if len(hull_faces) < 4:\n            return None\n\n        out_bm = bmesh.new()\n\n        vertex_map = {}\n\n        for v in hull_verts:\n\n            nv = out_bm.verts.new(\n                v.co.copy()\n            )\n\n            vertex_map[v] = nv\n\n        out_bm.verts.ensure_lookup_table()\n\n        for face in hull_faces:\n\n            verts = [\n                vertex_map[v]\n                for v in face.verts\n            ]\n\n            try:\n                out_bm.faces.new(\n                    verts\n                )\n            except ValueError:\n                pass\n\n        out_bm.faces.ensure_lookup_table()\n\n        if not out_bm.faces:\n            out_bm.free()\n            return None\n\n        mesh = bpy.data.meshes.new(\n            name + "_MESH"\n        )\n\n        out_bm.to_mesh(mesh)\n\n        out_bm.free()\n\n        mesh.update()\n\n        return mesh\n\n    finally:\n\n        bm.free()\n\n\n# ============================================================\n# Generate Fine UCX\n# ============================================================\n\ndef generate_collision(\n    render_mesh,\n    clean_name,\n    collection\n):\n\n    vertices, triangles = (\n        build_triangle_data(\n            render_mesh\n        )\n    )\n\n    if len(triangles) == 0:\n        raise RuntimeError(\n            "Render Mesh 没有有效三角面。"\n        )\n\n    print(\n        f"[INFO] Source Triangles  : "\n        f"{len(triangles)}"\n    )\n\n    clusters = build_spatial_clusters(\n        triangles,\n        vertices\n    )\n\n    print(\n        f"[INFO] Spatial Clusters  : "\n        f"{len(clusters)}"\n    )\n\n    collision_objects = []\n\n    for index, cluster in enumerate(\n        clusters\n    ):\n\n        # 收集这个局部空间块的真实网格顶点\n        vertex_ids = set()\n\n        for tri_id in cluster:\n\n            a, b, c, _ = triangles[\n                tri_id\n            ]\n\n            vertex_ids.add(a)\n            vertex_ids.add(b)\n            vertex_ids.add(c)\n\n        points = [\n            vertices[i]\n            for i in vertex_ids\n        ]\n\n        name = (\n            f"UCX_{clean_name}_"\n            f"{index:02d}"\n        )\n\n        mesh = create_convex_hull_mesh(\n            points,\n            name\n        )\n\n        if mesh is None:\n            continue\n\n        obj = bpy.data.objects.new(\n            name,\n            mesh\n        )\n\n        collection.objects.link(\n            obj\n        )\n\n        obj.location = (\n            0.0,\n            0.0,\n            0.0\n        )\n\n        obj.rotation_euler = (\n            0.0,\n            0.0,\n            0.0\n        )\n\n        obj.scale = (\n            1.0,\n            1.0,\n            1.0\n        )\n\n        obj.hide_render = True\n        obj.hide_viewport = (\n            not SHOW_GENERATED_COLLISION\n        )\n\n        collision_objects.append(\n            obj\n        )\n\n    if not collision_objects:\n        raise RuntimeError(\n            "没有生成有效 UCX。"\n        )\n\n    return collision_objects\n\n\n# ============================================================\n# Validation\n# ============================================================\n\ndef validate_uv(obj):\n\n    count = len(\n        obj.data.uv_layers\n    )\n\n    if count == 0:\n        raise RuntimeError(\n            "Render Mesh 没有 UV。"\n        )\n\n    return count\n\n\ndef validate_transform(obj):\n\n    if any(\n        abs(v) > 0.0001\n        for v in obj.location\n    ):\n        raise RuntimeError(\n            f"{obj.name}: Location 非 0"\n        )\n\n    if any(\n        abs(v) > 0.0001\n        for v in obj.rotation_euler\n    ):\n        raise RuntimeError(\n            f"{obj.name}: Rotation 非 0"\n        )\n\n    if any(\n        abs(v - 1.0) > 0.0001\n        for v in obj.scale\n    ):\n        raise RuntimeError(\n            f"{obj.name}: Scale 非 1"\n        )\n\n\ndef validate_collision(obj):\n\n    validate_transform(obj)\n\n    if len(obj.data.vertices) < 4:\n        raise RuntimeError(\n            f"{obj.name}: UCX 顶点不足"\n        )\n\n    if len(obj.data.polygons) < 4:\n        raise RuntimeError(\n            f"{obj.name}: UCX 面不足"\n        )\n\n\n# ============================================================\n# Export\n# ============================================================\n\ndef prepare_export_objects(\n    render_mesh,\n    collision_objects\n):\n    """\n    FBX 最终导出对象准备。\n\n    明确保证：\n        Render Mesh\n        +\n        所有 UCX\n    在同一个 Selection 中一次性导出。\n\n    不依赖 Collection 可见性，不依赖当前 UI 选择状态。\n    """\n\n    if render_mesh is None:\n        raise RuntimeError(\n            "Render Mesh 不存在，无法导出。"\n        )\n\n    if not collision_objects:\n        raise RuntimeError(\n            "没有 UCX Collision，禁止导出。"\n        )\n\n    expected_prefix = (\n        f"UCX_{render_mesh.name}_"\n    )\n\n    # ----------------------------------------\n    # 1. 检查所有 UCX 命名\n    # ----------------------------------------\n\n    for index, collision in enumerate(\n        collision_objects\n    ):\n\n        expected_name = (\n            f"{expected_prefix}"\n            f"{index:02d}"\n        )\n\n        if collision.name != expected_name:\n\n            # Blender 可能自动产生 .001\n            # 因此这里直接强制重命名。\n            collision.name = expected_name\n\n        if not collision.name.startswith(\n            expected_prefix\n        ):\n            raise RuntimeError(\n                f"UCX 命名错误："\n                f"{collision.name}\\n"\n                f"Render Mesh：{render_mesh.name}\\n"\n                f"要求前缀：{expected_prefix}"\n            )\n\n        # 确保 Collision 与 Render Mesh\n        # 位于完全相同的 Asset 空间\n        collision.location = (\n            0.0,\n            0.0,\n            0.0\n        )\n\n        collision.rotation_euler = (\n            0.0,\n            0.0,\n            0.0\n        )\n\n        collision.scale = (\n            1.0,\n            1.0,\n            1.0\n        )\n\n        # 强制保证 Blender FBX Export 不因隐藏状态跳过\n        collision.hide_viewport = False\n        collision.hide_render = False\n\n        try:\n            collision.hide_set(False)\n        except Exception:\n            pass\n\n        # 视口用线框显示，方便检查，\n        # 不改变 FBX 几何。\n        collision.display_type = \'WIRE\'\n\n    # Render Mesh 也必须可导出\n    render_mesh.hide_viewport = False\n    render_mesh.hide_render = False\n\n    try:\n        render_mesh.hide_set(False)\n    except Exception:\n        pass\n\n    export_objects = [\n        render_mesh\n    ] + list(collision_objects)\n\n    # ----------------------------------------\n    # 2. 强制清空 Selection\n    # ----------------------------------------\n\n    bpy.ops.object.select_all(\n        action=\'DESELECT\'\n    )\n\n    # ----------------------------------------\n    # 3. 强制选择 Render + 全部 UCX\n    # ----------------------------------------\n\n    for obj in export_objects:\n\n        if obj.type != \'MESH\':\n            raise RuntimeError(\n                f"导出对象不是 Mesh："\n                f"{obj.name}"\n            )\n\n        obj.select_set(True)\n\n    # Render Mesh 作为 Active Object\n    bpy.context.view_layer.objects.active = (\n        render_mesh\n    )\n\n    bpy.context.view_layer.update()\n\n    # ----------------------------------------\n    # 4. 最终 Selection Audit\n    # ----------------------------------------\n\n    selected_meshes = [\n        obj\n        for obj in bpy.context.selected_objects\n        if obj.type == \'MESH\'\n    ]\n\n    selected_names = [\n        obj.name\n        for obj in selected_meshes\n    ]\n\n    expected_names = [\n        obj.name\n        for obj in export_objects\n    ]\n\n    if set(selected_names) != set(\n        expected_names\n    ):\n        raise RuntimeError(\n            "FBX Selection Audit FAILED。\\n"\n            f"Expected：{expected_names}\\n"\n            f"Selected：{selected_names}"\n        )\n\n    if render_mesh.name not in selected_names:\n        raise RuntimeError(\n            "Render Mesh 没有进入最终 FBX Selection。"\n        )\n\n    selected_ucx = [\n        obj\n        for obj in selected_meshes\n        if obj.name.startswith(\n            expected_prefix\n        )\n    ]\n\n    if len(selected_ucx) != len(\n        collision_objects\n    ):\n        raise RuntimeError(\n            "并非所有 UCX 都进入最终 FBX Selection。\\n"\n            f"Expected UCX：{len(collision_objects)}\\n"\n            f"Selected UCX：{len(selected_ucx)}"\n        )\n\n    print(\n        "[INFO] FBX Selection Audit : PASS"\n    )\n\n    print(\n        f"[INFO] Selected Render     : "\n        f"{render_mesh.name}"\n    )\n\n    print(\n        f"[INFO] Selected UCX        : "\n        f"{len(selected_ucx)}"\n    )\n\n    for obj in selected_ucx:\n\n        print(\n            f"[INFO]   -> {obj.name}"\n        )\n\n    return export_objects\n\n\ndef export_fbx(\n    render_mesh,\n    collision_objects,\n    filepath\n):\n\n    # ----------------------------------------\n    # 强制准备最终导出对象\n    # ----------------------------------------\n\n    export_objects = prepare_export_objects(\n        render_mesh,\n        collision_objects\n    )\n\n    print(\n        "[INFO] FBX Contents        : "\n        f"{len(export_objects)} Mesh Objects"\n    )\n\n    print(\n        "[INFO] FBX Contents        : "\n        "1 Render + "\n        f"{len(collision_objects)} UCX"\n    )\n\n    # ----------------------------------------\n    # 一次性导出\n    #\n    # Render Mesh + UCX\n    # 必须在同一个 FBX 文件里。\n    # ----------------------------------------\n\n    bpy.ops.export_scene.fbx(\n        filepath=filepath,\n        **FBX_SETTINGS\n    )\n\n    print(\n        "[INFO] FBX Export Contents : "\n        "Render + UCX SAME FILE"\n    )\n\n    return export_objects\n\n\n# ============================================================\n# Main\n# ============================================================\n\ndef export_single_asset(render_mesh, collection, asset_index, asset_total):\n\n    print("\\n" + "=" * 80)\n    print(\n        f"BLENDER -> UE FBX V0.13 | "\n        f"ASSET {asset_index}/{asset_total}"\n    )\n    print(\n        "Render Mesh + Concavity-Aware Multi-Convex UCX"\n    )\n    print("=" * 80)\n\n    print(\n        f"[INFO] Collection        : "\n        f"{collection.name}"\n    )\n\n    print(\n        f"[INFO] Asset Index       : "\n        f"{asset_index}/{asset_total}"\n    )\n\n    source_name = render_mesh.name\n\n    clean_name = sanitize_asset_name(\n        source_name\n    )\n\n    print(\n        f"[INFO] Source Object     : "\n        f"{source_name}"\n    )\n\n    print(\n        f"[INFO] Asset Name        : "\n        f"{clean_name}"\n    )\n\n    # ③ UV\n    uv_count = validate_uv(\n        render_mesh\n    )\n\n    print(\n        f"[INFO] UV Channels       : "\n        f"PASS ({uv_count})"\n    )\n\n    # ④ Transform\n    apply_rotation_scale(\n        render_mesh\n    )\n\n    print(\n        "[INFO] Rotation / Scale  : "\n        "APPLIED"\n    )\n\n    center = center_geometry(\n        render_mesh\n    )\n\n    print(\n        "[INFO] Mesh Center -> Origin : "\n        "PASS"\n    )\n\n    print(\n        f"[INFO] Center Offset     : "\n        f"({center.x:.6f}, "\n        f"{center.y:.6f}, "\n        f"{center.z:.6f})"\n    )\n\n    normalize_transform(\n        render_mesh\n    )\n\n    print(\n        "[INFO] Origin -> World 0  : "\n        "PASS"\n    )\n\n    # ⑤ Remove old UCX\n    if REBUILD_COLLISION:\n\n        removed = remove_old_ucx(\n            clean_name\n        )\n\n        print(\n            f"[INFO] Old UCX Removed   : "\n            f"{removed}"\n        )\n\n    # ⑥ Generate fine collision\n    collision_objects = (\n        generate_collision(\n            render_mesh,\n            clean_name,\n            collection\n        )\n    )\n\n    print(\n        f"[INFO] UCX Generated     : "\n        f"{len(collision_objects)}"\n    )\n\n    # ⑦ Validate\n    validate_transform(\n        render_mesh\n    )\n\n    for collision in collision_objects:\n        validate_collision(\n            collision\n        )\n\n    print(\n        "[INFO] Render Transform  : "\n        "PASS"\n    )\n\n    print(\n        "[INFO] UCX Geometry      : "\n        "PASS"\n    )\n\n    print(\n        "[INFO] UCX Transform     : "\n        "PASS"\n    )\n\n    # ⑧ Output\n    asset_dir = os.path.join(\n        EXPORT_ROOT,\n        clean_name\n    )\n\n    os.makedirs(\n        asset_dir,\n        exist_ok=True\n    )\n\n    fbx_path = os.path.join(\n        asset_dir,\n        clean_name + ".fbx"\n    )\n\n    print(\n        f"[INFO] Export Objects    : "\n        f"1 Render + "\n        f"{len(collision_objects)} UCX"\n    )\n\n    print(\n        "[INFO] FBX Export        : "\n        "START"\n    )\n\n    export_objects = export_fbx(\n        render_mesh,\n        collision_objects,\n        fbx_path\n    )\n\n    # ⑨ Verify\n    if not os.path.isfile(\n        fbx_path\n    ):\n        raise RuntimeError(\n            "FBX 文件不存在。"\n        )\n\n    file_size = os.path.getsize(\n        fbx_path\n    )\n\n    print(\n        "[INFO] FBX File Contents   : "\n        "Render + All UCX"\n    )\n\n    if file_size <= 10 * 1024:\n        raise RuntimeError(\n            f"FBX 文件异常："\n            f"{file_size / 1024:.2f} KB"\n        )\n\n    # ⑩ Final Log\n    print("-" * 80)\n\n    print(\n        f"[INFO] Render Mesh       : 1"\n    )\n\n    print(\n        f"[INFO] UCX Hulls         : "\n        f"{len(collision_objects)}"\n    )\n\n    print(\n        f"[INFO] Source Triangles  : "\n        f"{len(render_mesh.data.polygons)}"\n    )\n\n    print(\n        f"[INFO] UV Channels       : "\n        f"PASS ({uv_count})"\n    )\n\n    print(\n        "[INFO] Mesh Center       : PASS"\n    )\n\n    print(\n        "[INFO] World Origin      : PASS"\n    )\n\n    print(\n        "[INFO] Fine Collision    : PASS"\n    )\n\n    print(\n        "[INFO] FBX File           : PASS"\n    )\n\n    print(\n        f"[INFO] File Size         : "\n        f"{file_size / 1024:.2f} KB"\n    )\n\n    print("-" * 80)\n\n    print(\n        f"[STATUS] EXPORT SUCCESS -> "\n        f"{clean_name}.fbx"\n    )\n\n    print(\n        f"[STATUS] {fbx_path}"\n    )\n\n    print("=" * 80)\n\n    return {\n        "clean_name": clean_name,\n        "fbx_path": fbx_path,\n        "file_size": file_size,\n        "uv_count": uv_count,\n        "collision_count": len(collision_objects),\n        "triangle_count": len(render_mesh.data.polygons),\n    }\n\n\ndef export_asset():\n\n    print("\\n" + "#" * 80)\n    print(\n        "BLENDER -> UE FBX V0.13 BATCH"\n    )\n    print(\n        "Collection Batch Export | Every Render Mesh"\n    )\n    print("#" * 80)\n\n    # ① Collection\n    collection = get_collection()\n\n    print(\n        f"[INFO] Collection        : "\n        f"{collection.name}"\n    )\n\n    # ② 一次性取得 Collection 中全部 Render Mesh\n    render_meshes = get_render_meshes(\n        collection\n    )\n\n    total = len(render_meshes)\n\n    print(\n        f"[INFO] Render Mesh Count : "\n        f"{total}"\n    )\n\n    for index, obj in enumerate(\n        render_meshes,\n        start=1\n    ):\n        print(\n            f"[INFO]   [{index}/{total}] "\n            f"{obj.name}"\n        )\n\n    results = []\n    failed = []\n\n    # ③ 逐个资产执行原有导出逻辑\n    for index, render_mesh in enumerate(\n        render_meshes,\n        start=1\n    ):\n\n        try:\n\n            result = export_single_asset(\n                render_mesh,\n                collection,\n                index,\n                total\n            )\n\n            results.append(result)\n\n        except Exception as e:\n\n            failed.append(\n                (\n                    render_mesh.name,\n                    str(e)\n                )\n            )\n\n            print("\\n" + "!" * 80)\n            print(\n                f"[STATUS] ASSET FAILED "\n                f"{index}/{total}"\n            )\n            print(\n                f"[ERROR] {render_mesh.name}: {e}"\n            )\n            print("!" * 80)\n\n            # 单个资产失败不影响后续资产继续导出\n            continue\n\n    # ④ Batch Final Log\n    print("\\n" + "#" * 80)\n    print(\n        f"[BATCH STATUS] SUCCESS = "\n        f"{len(results)} / {total}"\n    )\n    print(\n        f"[BATCH STATUS] FAILED  = "\n        f"{len(failed)} / {total}"\n    )\n\n    if results:\n\n        print("-" * 80)\n        print("[BATCH] Exported Assets:")\n\n        for result in results:\n\n            print(\n                f"[OK] {result[\'clean_name\']}.fbx | "\n                f"UCX={result[\'collision_count\']} | "\n                f"{result[\'file_size\'] / 1024:.2f} KB"\n            )\n\n    if failed:\n\n        print("-" * 80)\n        print("[BATCH] Failed Assets:")\n\n        for source_name, error_text in failed:\n\n            print(\n                f"[FAILED] {source_name} | "\n                f"{error_text}"\n            )\n\n        print(\n            "[BATCH STATUS] EXPORT COMPLETED WITH FAILURES"\n        )\n\n    else:\n\n        print(\n            "[BATCH STATUS] EXPORT SUCCESS"\n        )\n\n    print("#" * 80)\n\n\n'

PBR_SOURCE = '\nimport bpy\nimport os\nimport re\nfrom collections import defaultdict, deque\n\n# ============================================================\n# Blender -> UE PBR Texture Extractor V0.1\n# 单体 Mesh 实验版\n#\n# Collection 5 中选择 1 个 Mesh：\n#   Mesh\n#    -> Material Slots\n#    -> Material 去重\n#    -> Node Tree 反向追踪 Image Texture\n#    -> PBR 通道识别\n#    -> 导出到指定 FBX 资产文件夹\n#\n# 本脚本：\n#   不修改 Mesh\n#   不修改 UV\n#   不导出 FBX\n#   不生成 UCX\n# ============================================================\n\nCOLLECTION_NAME = "Collection 4"\n\n# 当前实验资产对应的 FBX 文件夹\nOUTPUT_ROOT = r"C:\\Users\\Administrator\\Desktop\\元神\\广西\\fbx\\collection_4"\n\n# 留空 = 使用当前唯一选中的 Mesh\nTARGET_OBJECT_NAME = ""\n\n# 所有贴图统一保存为 PNG\nOUTPUT_FORMAT = "PNG"\n\nCHANNEL_SUFFIX = {\n    "D": "_D",\n    "N": "_N",\n    "R": "_R",\n    "M": "_M",\n    "AO": "_AO",\n    "H": "_H",\n    "ORM": "_ORM",\n}\n\n\n# ============================================================\n# Name\n# ============================================================\n\ndef sanitize_name(name):\n    name = re.sub(r\'[\\\\/:*?"<>|]\', "_", name)\n    name = re.sub(r"\\s+", "_", name)\n    name = re.sub(r"_+", "_", name)\n    name = name.strip("_")\n    return name or "Unnamed"\n\n\ndef material_folder_name(material_name):\n    name = sanitize_name(material_name)\n    return name if name.startswith("M_") else "M_" + name\n\n\ndef texture_base_name(material_name):\n    name = sanitize_name(material_name)\n    return name[2:] if name.startswith("M_") else name\n\n\ndef texture_filename(material_name, channel, index=1, total=1):\n    base = texture_base_name(material_name)\n    suffix = CHANNEL_SUFFIX[channel]\n    if total == 1:\n        return f"T_{base}{suffix}.png"\n    return f"T_{base}{suffix}_{index:02d}.png"\n\n\n# ============================================================\n# Object / Collection\n# ============================================================\n\ndef get_collection():\n    collection = bpy.data.collections.get(COLLECTION_NAME)\n    if collection is None:\n        raise RuntimeError(f"找不到 Collection：{COLLECTION_NAME}")\n    return collection\n\n\ndef get_target_meshes(collection):\n    """\n    获取指定 Collection 下全部 Render Mesh。\n    以 UCX_ 开头的碰撞 Mesh 不参与 PBR 提取。\n    """\n    meshes = [\n        obj\n        for obj in collection.objects\n        if obj.type == "MESH"\n        and not obj.name.upper().startswith("UCX_")\n    ]\n\n    if not meshes:\n        raise RuntimeError(\n            f"Collection \'{COLLECTION_NAME}\' 中没有找到 Mesh。"\n        )\n\n    return meshes\n\n\n# ============================================================\n# Material Slots\n# ============================================================\n\ndef scan_material_slots(obj):\n    records = []\n\n    for slot_index, slot in enumerate(obj.material_slots):\n        material = slot.material\n\n        if material is None:\n            print(f"[SKIP] Slot {slot_index:02d}：空材质槽")\n            continue\n\n        records.append((slot_index, material))\n\n    return records\n\n\n# ============================================================\n# Node Tree Trace\n# ============================================================\n\ndef find_upstream_images(start_socket):\n    """\n    从指定 Socket 向上游递归追踪。\n    会穿透 ColorRamp / Mapping / Reroute / Normal Map /\n    Math / Mix / Separate RGB / 其它中间节点。\n    最终只把真实 Image Texture 节点作为贴图来源。\n    """\n    if start_socket is None:\n        return []\n\n    queue = deque([start_socket])\n    visited_sockets = set()\n    visited_nodes = set()\n    images = []\n\n    while queue:\n        socket = queue.popleft()\n\n        socket_key = (\n            socket.node.as_pointer(),\n            socket.identifier,\n            socket.name,\n        )\n        if socket_key in visited_sockets:\n            continue\n        visited_sockets.add(socket_key)\n\n        if not socket.is_linked:\n            continue\n\n        for link in socket.links:\n            node = link.from_node\n\n            if node.type == "TEX_IMAGE":\n                if node.image is not None:\n                    images.append(node.image)\n                continue\n\n            node_key = node.as_pointer()\n            if node_key in visited_nodes:\n                continue\n            visited_nodes.add(node_key)\n\n            for input_socket in node.inputs:\n                if input_socket.is_linked:\n                    queue.append(input_socket)\n\n    unique = []\n    seen = set()\n\n    for image in images:\n        key = image.as_pointer()\n        if key in seen:\n            continue\n        seen.add(key)\n        unique.append(image)\n\n    return unique\n\n\ndef find_principled_nodes(material):\n    if not material.use_nodes or material.node_tree is None:\n        return []\n\n    return [\n        node for node in material.node_tree.nodes\n        if node.type == "BSDF_PRINCIPLED"\n    ]\n\n\ndef trace_pbr(material):\n    """\n    返回：\n        D / N / R / M / AO / H / ORM\n    各通道对应的 Image datablock。\n    """\n    result = defaultdict(list)\n\n    principled_nodes = find_principled_nodes(material)\n\n    for principled in principled_nodes:\n        socket_map = {\n            "Base Color": "D",\n            "Normal": "N",\n            "Roughness": "R",\n            "Metallic": "M",\n        }\n\n        for socket_name, channel in socket_map.items():\n            socket = principled.inputs.get(socket_name)\n            if socket is None:\n                continue\n\n            for image in find_upstream_images(socket):\n                result[channel].append(image)\n\n    # Height / Displacement\n    for node in material.node_tree.nodes:\n        if node.type != "DISPLACEMENT":\n            continue\n\n        height_socket = node.inputs.get("Height")\n        if height_socket is None:\n            continue\n\n        for image in find_upstream_images(height_socket):\n            result["H"].append(image)\n\n    # AO：Blender Principled 没有标准 AO 输入。\n    # 本实验版通过节点/图片名称辅助识别明确命名的 AO 图片。\n    for node in material.node_tree.nodes:\n        if node.type != "TEX_IMAGE" or node.image is None:\n            continue\n\n        text = " ".join([\n            node.name or "",\n            node.label or "",\n            node.image.name or "",\n            node.image.filepath or "",\n        ]).lower()\n\n        if any(token in text for token in (\n            "_ao", "ao_", "ao.", "ambientocclusion", "ambient_occlusion"\n        )):\n            result["AO"].append(node.image)\n\n    # 已有 ORM/RMA/MRA 复合图：只识别并导出，不在本版生成新 ORM。\n    candidates = set()\n    for images in result.values():\n        candidates.update(img.as_pointer() for img in images)\n\n    for node in material.node_tree.nodes:\n        if node.type != "TEX_IMAGE" or node.image is None:\n            continue\n\n        text = " ".join([\n            node.name or "",\n            node.label or "",\n            node.image.name or "",\n            node.image.filepath or "",\n        ]).lower()\n\n        if any(token in text for token in (\n            "orm", "_orm", "rma", "_rma", "mra", "_mra"\n        )):\n            result["ORM"].append(node.image)\n\n    # 每个通道内部去重\n    for channel in list(result.keys()):\n        unique = []\n        seen = set()\n        for image in result[channel]:\n            key = image.as_pointer()\n            if key in seen:\n                continue\n            seen.add(key)\n            unique.append(image)\n        result[channel] = unique\n\n    return result\n\n\n# ============================================================\n# Image Save\n# ============================================================\n\ndef validate_image(image):\n    if image is None:\n        raise RuntimeError("Image 为空")\n\n    if image.packed_file is not None:\n        return\n\n    path = image.filepath_raw or image.filepath\n    if not path:\n        raise RuntimeError("贴图没有有效路径")\n\n    abs_path = bpy.path.abspath(path)\n    if not os.path.isfile(abs_path):\n        raise RuntimeError(f"源文件不存在：{abs_path}")\n\n\ndef save_image(image, destination):\n    validate_image(image)\n\n    os.makedirs(os.path.dirname(destination), exist_ok=True)\n\n    original_format = image.file_format\n    try:\n        image.file_format = OUTPUT_FORMAT\n        image.save(filepath=destination, save_copy=True)\n    finally:\n        image.file_format = original_format\n\n    if not os.path.isfile(destination):\n        raise RuntimeError(f"写出失败：{destination}")\n\n    size = os.path.getsize(destination)\n    if size <= 0:\n        raise RuntimeError(f"输出为 0 字节：{destination}")\n\n    return size\n\n\n# ============================================================\n# Material Export\n# ============================================================\n\ndef export_material(material, slot_index, output_root=None):\n    if output_root is None:\n        output_root = OUTPUT_ROOT\n\n    folder_name = material_folder_name(material.name)\n    material_dir = os.path.join(output_root, folder_name)\n    os.makedirs(material_dir, exist_ok=True)\n\n    print("")\n    print("-" * 80)\n    print(f"[MATERIAL] Slot      : {slot_index:02d}")\n    print(f"[MATERIAL] Name      : {material.name}")\n    print(f"[MATERIAL] Directory : {material_dir}")\n\n    pbr = trace_pbr(material)\n\n    exported = []\n    skipped = []\n    failed = []\n\n    for channel in ("D", "N", "R", "M", "AO", "H", "ORM"):\n        images = pbr.get(channel, [])\n\n        if not images:\n            print(f"[PBR] {channel:<4} : NOT FOUND")\n            continue\n\n        print(f"[PBR] {channel:<4} : {len(images)} image(s)")\n\n        for index, image in enumerate(images, start=1):\n            filename = texture_filename(\n                material.name,\n                channel,\n                index,\n                len(images)\n            )\n            destination = os.path.join(material_dir, filename)\n\n            if os.path.isfile(destination):\n                print(f"[SKIP] Exists : {filename}")\n                skipped.append(filename)\n                continue\n\n            try:\n                size = save_image(image, destination)\n                print(\n                    f"[EXPORT] {filename} | "\n                    f"{size / 1024:.2f} KB | "\n                    f"source={image.name}"\n                )\n                exported.append(filename)\n            except Exception as exc:\n                print(\n                    f"[WARNING] {material.name} | "\n                    f"{channel} | {image.name} | {exc}"\n                )\n                failed.append(\n                    f"{filename} | {exc}"\n                )\n\n    return {\n        "material": material.name,\n        "folder": material_dir,\n        "exported": exported,\n        "skipped": skipped,\n        "failed": failed,\n    }\n\n\n# ============================================================\n# Main\n# ============================================================\n\ndef export_collection_pbr():\n    print("")\n    print("=" * 80)\n    print("BLENDER -> UE PBR TEXTURE EXPORT V0.2")\n    print("Collection 5 / All Mesh PBR Extraction")\n    print("=" * 80)\n\n    os.makedirs(OUTPUT_ROOT, exist_ok=True)\n\n    collection = get_collection()\n    meshes = get_target_meshes(collection)\n\n    print(f"[INFO] Collection       : {collection.name}")\n    print(f"[INFO] Mesh Count       : {len(meshes)}")\n    print(f"[INFO] Output Root      : {OUTPUT_ROOT}")\n\n    all_results = []\n    total_exported = 0\n    total_skipped = 0\n    total_failed = 0\n\n    for mesh_index, obj in enumerate(meshes, start=1):\n\n        # 每个 Mesh 单独建立 SM_ 资产目录\n        mesh_name = sanitize_name(obj.name)\n        if not mesh_name.startswith("SM_"):\n            mesh_name = "SM_" + mesh_name\n\n        mesh_output_root = os.path.join(\n            OUTPUT_ROOT,\n            mesh_name\n        )\n        os.makedirs(mesh_output_root, exist_ok=True)\n\n        print("")\n        print("#" * 80)\n        print(\n            f"[ASSET {mesh_index}/{len(meshes)}] "\n            f"{obj.name}"\n        )\n        print(\n            f"[ASSET] Output Root : "\n            f"{mesh_output_root}"\n        )\n        print("#" * 80)\n\n        print(\n            f"[INFO] Material Slots  : "\n            f"{len(obj.material_slots)}"\n        )\n\n        records = scan_material_slots(obj)\n\n        print(\n            f"[INFO] Valid Materials : "\n            f"{len(records)}"\n        )\n\n        # 保持原来的：同一 Mesh 内共享同一 Material 只处理一次\n        processed_materials = set()\n        mesh_results = []\n\n        for slot_index, material in records:\n\n            material_key = material.as_pointer()\n\n            if material_key in processed_materials:\n                print(\n                    f"[SKIP] Slot {slot_index:02d} -> "\n                    f"{material.name} | Duplicate Material"\n                )\n                continue\n\n            processed_materials.add(material_key)\n\n            result = export_material(\n                material,\n                slot_index,\n                mesh_output_root\n            )\n\n            mesh_results.append(result)\n\n            total_exported += len(result["exported"])\n            total_skipped += len(result["skipped"])\n            total_failed += len(result["failed"])\n\n        all_results.append(\n            {\n                "mesh": obj.name,\n                "folder": mesh_output_root,\n                "materials": mesh_results,\n            }\n        )\n\n    # ========================================================\n    # Batch Log\n    # ========================================================\n\n    log_path = os.path.join(\n        OUTPUT_ROOT,\n        "PBR_Texture_Export_Batch_Log.txt"\n    )\n\n    with open(log_path, "w", encoding="utf-8") as log:\n\n        log.write(\n            "BLENDER -> UE PBR TEXTURE EXPORT V0.2\\n"\n        )\n        log.write("=" * 80 + "\\n")\n        log.write(\n            f"Collection: {collection.name}\\n"\n        )\n        log.write(\n            f"Mesh Count: {len(meshes)}\\n"\n        )\n        log.write(\n            f"Output Root: {OUTPUT_ROOT}\\n"\n        )\n        log.write("=" * 80 + "\\n\\n")\n\n        for asset in all_results:\n\n            log.write(\n                f"Mesh: {asset[\'mesh\']}\\n"\n            )\n            log.write(\n                f"Folder: {asset[\'folder\']}\\n"\n            )\n\n            for result in asset["materials"]:\n\n                log.write(\n                    f"  Material: {result[\'material\']}\\n"\n                )\n\n                if result["exported"]:\n                    log.write("  Exported:\\n")\n                    for item in result["exported"]:\n                        log.write(\n                            f"    {item}\\n"\n                        )\n\n                if result["skipped"]:\n                    log.write("  Skipped:\\n")\n                    for item in result["skipped"]:\n                        log.write(\n                            f"    {item}\\n"\n                        )\n\n                if result["failed"]:\n                    log.write("  Failed:\\n")\n                    for item in result["failed"]:\n                        log.write(\n                            f"    {item}\\n"\n                        )\n\n            log.write("\\n")\n\n    print("")\n    print("=" * 80)\n    print("[STATUS] PBR BATCH EXPORT FINISHED")\n    print(f"[INFO] Mesh Count       : {len(meshes)}")\n    print(f"[INFO] Exported Images  : {total_exported}")\n    print(f"[INFO] Skipped Images   : {total_skipped}")\n    print(f"[INFO] Failed Images    : {total_failed}")\n    print(f"[INFO] Log              : {log_path}")\n    print("=" * 80)\n\n\n'

# ============================================================
# Isolated module loading
# ============================================================

FBX_NS = {
    "__name__": "__embedded_fbx_pipeline__",
    "__file__": "<embedded_fbx_pipeline>",
}

PBR_NS = {
    "__name__": "__embedded_pbr_pipeline__",
    "__file__": "<embedded_pbr_pipeline>",
}

exec(FBX_SOURCE, FBX_NS)
exec(PBR_SOURCE, PBR_NS)

# ============================================================
# Controller utilities
# ============================================================

def controller_get_collection():
    collection = bpy.data.collections.get(
        COLLECTION_NAME
    )

    if collection is None:
        raise RuntimeError(
            f"找不到 Collection：{COLLECTION_NAME}"
        )

    return collection


def controller_get_render_meshes(collection):
    return [
        obj
        for obj in collection.objects
        if obj.type == "MESH"
        and not obj.name.upper().startswith("UCX_")
    ]


def controller_asset_name(obj):
    return FBX_NS["sanitize_asset_name"](
        obj.name
    )


def controller_asset_dir(obj):
    return os.path.join(
        EXPORT_ROOT,
        controller_asset_name(obj)
    )


def controller_fbx_path(obj):
    asset_name = controller_asset_name(obj)

    return os.path.join(
        controller_asset_dir(obj),
        asset_name + ".fbx"
    )


def controller_pbr_asset(
    obj,
    collection,
    mesh_index,
    mesh_total
):
    """
    PHASE 2：
    使用第二版 PBR 脚本的原始函数：
        scan_material_slots()
        export_material()
    不改变它们内部逻辑，只改变输出根目录。
    """

    asset_dir = controller_asset_dir(obj)

    texture_root = os.path.join(
        asset_dir,
        TEXTURE_ROOT_NAME
    )

    os.makedirs(
        texture_root,
        exist_ok=True
    )

    print("")
    print("=" * 80)
    print(
        f"[PHASE 2] PBR "
        f"{mesh_index}/{mesh_total}"
    )
    print(
        f"[PBR] Mesh         : "
        f"{obj.name}"
    )
    print(
        f"[PBR] Texture Root : "
        f"{texture_root}"
    )
    print("=" * 80)

    records = PBR_NS["scan_material_slots"](
        obj
    )

    print(
        f"[PBR] Material Slots : "
        f"{len(obj.material_slots)}"
    )

    print(
        f"[PBR] Valid Materials: "
        f"{len(records)}"
    )

    processed_materials = set()
    results = []

    for slot_index, material in records:

        material_key = material.as_pointer()

        if material_key in processed_materials:

            print(
                f"[PBR][SKIP] Slot "
                f"{slot_index:02d} -> "
                f"{material.name} | "
                f"Duplicate Material"
            )

            continue

        processed_materials.add(
            material_key
        )

        result = PBR_NS["export_material"](
            material,
            slot_index,
            texture_root
        )

        results.append(
            result
        )

    exported = sum(
        len(result["exported"])
        for result in results
    )

    skipped = sum(
        len(result["skipped"])
        for result in results
    )

    failed = sum(
        len(result["failed"])
        for result in results
    )

    # 当前 Mesh 的 PBR Log
    log_path = os.path.join(
        asset_dir,
        "PBR_Texture_Export_Log.txt"
    )

    with open(
        log_path,
        "w",
        encoding="utf-8"
    ) as log:

        log.write(
            "BLENDER -> UE PBR TEXTURE EXPORT\n"
        )
        log.write("=" * 80 + "\n")
        log.write(
            f"Collection: {collection.name}\n"
        )
        log.write(
            f"Mesh: {obj.name}\n"
        )
        log.write(
            f"Texture Root: {texture_root}\n"
        )
        log.write(
            f"Material Slots: "
            f"{len(obj.material_slots)}\n"
        )
        log.write(
            f"Unique Materials: "
            f"{len(results)}\n"
        )
        log.write("=" * 80 + "\n\n")

        for result in results:

            log.write(
                f"Material: "
                f"{result['material']}\n"
            )

            log.write(
                f"Folder: "
                f"{result['folder']}\n"
            )

            if result["exported"]:
                log.write("Exported:\n")

                for item in result["exported"]:
                    log.write(
                        f"  {item}\n"
                    )

            if result["skipped"]:
                log.write("Skipped:\n")

                for item in result["skipped"]:
                    log.write(
                        f"  {item}\n"
                    )

            if result["failed"]:
                log.write("Failed:\n")

                for item in result["failed"]:
                    log.write(
                        f"  {item}\n"
                    )

            log.write("\n")

    print(
        f"[PBR] Exported : {exported}"
    )
    print(
        f"[PBR] Skipped  : {skipped}"
    )
    print(
        f"[PBR] Failed   : {failed}"
    )
    print(
        f"[PBR] Log      : {log_path}"
    )

    return {
        "mesh": obj.name,
        "texture_root": texture_root,
        "unique_materials": len(results),
        "exported": exported,
        "skipped": skipped,
        "failed": failed,
        "log_path": log_path,
    }


# ============================================================
# Main Controller
# ============================================================

def run_pipeline():

    print("")
    print("#" * 80)
    print(
        "BLENDER -> UE COLLECTION 4 "
        "SEQUENTIAL PIPELINE V1"
    )
    print(
        "PHASE 1 = ORIGINAL FBX + UCX"
    )
    print(
        "PHASE 2 = ORIGINAL PBR TEXTURE EXPORT"
    )
    print("#" * 80)

    os.makedirs(
        EXPORT_ROOT,
        exist_ok=True
    )

    collection = controller_get_collection()
    render_meshes = controller_get_render_meshes(
        collection
    )

    total = len(render_meshes)

    if total == 0:
        raise RuntimeError(
            f"Collection '{COLLECTION_NAME}' "
            "中没有 Render Mesh。"
        )

    # --------------------------------------------------------
    # Configure original FBX script WITHOUT changing its logic
    # --------------------------------------------------------
    FBX_NS["COLLECTION_NAME"] = COLLECTION_NAME
    FBX_NS["EXPORT_ROOT"] = EXPORT_ROOT

    # --------------------------------------------------------
    # PHASE 1
    # 调用第一版脚本原本的 export_asset()
    # --------------------------------------------------------
    print("")
    print("#" * 80)
    print("[PHASE 1] START | ORIGINAL FBX + UCX")
    print("#" * 80)

    phase1_result = FBX_NS["export_asset"]()

    # 原始 export_asset() 负责自身的批量处理并打印成功/失败。
    # 这里不依赖其返回值，而是通过最终 FBX 文件存在性进行二次核对。
    phase1_success = []
    phase1_failed = []

    for obj in render_meshes:

        fbx_path = controller_fbx_path(
            obj
        )

        if os.path.isfile(fbx_path):

            phase1_success.append(
                {
                    "object": obj,
                    "fbx_path": fbx_path,
                    "asset_dir": controller_asset_dir(obj),
                }
            )

        else:

            phase1_failed.append(
                (
                    obj.name,
                    fbx_path
                )
            )

    print("")
    print(
        f"[PHASE 1] VERIFIED SUCCESS : "
        f"{len(phase1_success)}/{total}"
    )

    print(
        f"[PHASE 1] VERIFIED FAILED  : "
        f"{len(phase1_failed)}/{total}"
    )

    # --------------------------------------------------------
    # Strict gate
    # --------------------------------------------------------
    if (
        REQUIRE_ALL_FBX_SUCCESS_BEFORE_PBR
        and phase1_failed
    ):

        print("")
        print("!" * 80)
        print(
            "[PIPELINE STOPPED] "
            "PHASE 1 未全部成功，"
            "因此不执行 PHASE 2 PBR。"
        )

        for name, path in phase1_failed:

            print(
                f"[FAILED FBX] {name}"
            )

            print(
                f"              {path}"
            )

        print("!" * 80)

        return

    # --------------------------------------------------------
    # PHASE 2
    # 逐个调用第二版脚本的 PBR 核心函数
    # --------------------------------------------------------
    print("")
    print("#" * 80)
    print("[PHASE 2] START | ORIGINAL PBR TEXTURE LOGIC")
    print("#" * 80)

    pbr_success = []
    pbr_failed = []

    for index, item in enumerate(
        phase1_success,
        start=1
    ):

        obj = item["object"]

        try:

            result = controller_pbr_asset(
                obj,
                collection,
                index,
                len(phase1_success)
            )

            pbr_success.append(
                result
            )

        except Exception as exc:

            pbr_failed.append(
                (
                    obj.name,
                    str(exc)
                )
            )

            print("")
            print("!" * 80)
            print(
                f"[PHASE 2] FAILED "
                f"{index}/{len(phase1_success)}"
            )
            print(
                f"[ERROR] {obj.name}: {exc}"
            )
            print("!" * 80)

            continue

    # --------------------------------------------------------
    # Controller summary log
    # --------------------------------------------------------
    summary_path = os.path.join(
        EXPORT_ROOT,
        "Collection_Export_Controller_Log.txt"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8"
    ) as log:

        log.write(
            "BLENDER -> UE COLLECTION 4 "
            "SEQUENTIAL PIPELINE V1\n"
        )
        log.write("=" * 80 + "\n")
        log.write(
            f"Collection: {collection.name}\n"
        )
        log.write(
            f"Total Meshes: {total}\n"
        )
        log.write(
            f"Phase 1 FBX Success: "
            f"{len(phase1_success)}\n"
        )
        log.write(
            f"Phase 1 FBX Failed: "
            f"{len(phase1_failed)}\n"
        )
        log.write(
            f"Phase 2 PBR Success: "
            f"{len(pbr_success)}\n"
        )
        log.write(
            f"Phase 2 PBR Failed: "
            f"{len(pbr_failed)}\n"
        )
        log.write("=" * 80 + "\n\n")

        if phase1_failed:

            log.write(
                "PHASE 1 FAILED:\n"
            )

            for name, path in phase1_failed:

                log.write(
                    f"  {name}\n"
                )

                log.write(
                    f"    Expected FBX: {path}\n"
                )

            log.write("\n")

        if pbr_failed:

            log.write(
                "PHASE 2 FAILED:\n"
            )

            for name, error in pbr_failed:

                log.write(
                    f"  {name}\n"
                )

                log.write(
                    f"    ERROR: {error}\n"
                )

            log.write("\n")

        for result in pbr_success:

            log.write(
                f"[PBR OK] {result['mesh']}\n"
            )

            log.write(
                f"  Texture Root: "
                f"{result['texture_root']}\n"
            )

            log.write(
                f"  Materials: "
                f"{result['unique_materials']}\n"
            )

            log.write(
                f"  Exported: "
                f"{result['exported']}\n"
            )

            log.write(
                f"  Skipped: "
                f"{result['skipped']}\n"
            )

            log.write(
                f"  Failed: "
                f"{result['failed']}\n\n"
            )

    print("")
    print("#" * 80)
    print(
        f"[FINAL] PHASE 1 FBX SUCCESS : "
        f"{len(phase1_success)}/{total}"
    )
    print(
        f"[FINAL] PHASE 1 FBX FAILED  : "
        f"{len(phase1_failed)}/{total}"
    )
    print(
        f"[FINAL] PHASE 2 PBR SUCCESS : "
        f"{len(pbr_success)}/{len(phase1_success)}"
    )
    print(
        f"[FINAL] PHASE 2 PBR FAILED  : "
        f"{len(pbr_failed)}/{len(phase1_success)}"
    )
    print(
        f"[FINAL] SUMMARY LOG         : "
        f"{summary_path}"
    )

    if phase1_failed or pbr_failed:

        print(
            "[FINAL STATUS] "
            "EXPORT COMPLETED WITH FAILURES"
        )

    else:

        print(
            "[FINAL STATUS] "
            "EXPORT SUCCESS"
        )

    print("#" * 80)


# ============================================================
# Execute
# ============================================================

try:
    run_pipeline()

except Exception as exc:

    print("")
    print("!" * 80)
    print(
        "[PIPELINE ERROR]"
    )
    print(
        str(exc)
    )
    print(
        traceback.format_exc()
    )
    print("!" * 80)

    raise
