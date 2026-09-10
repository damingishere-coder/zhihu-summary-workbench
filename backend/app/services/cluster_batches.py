"""Merge batch-local directions without dropping original claim provenance."""
from backend.app.schemas.analysis import ClusterRefinementItem, ClusterSourceRelation


GLOBAL_MERGE_INSTRUCTION = """这是跨批次合并阶段。每项输入是前一阶段得到的观点方向，index 是本轮索引。
把不同批次里的重复、同义方向合并为全局可比较的观点分类，通常为8-12类；不可把批次当作分类依据。
每个本轮索引必须且只能分配一次，保留独立的少数观点和相反判断。
标题只能表达一个可独立认同或反对的核心判断，不得把多个不同命题拼接后统计支持人数。
只归并方向，不推测回答作者人数；source_relations 表达输入方向与最终核心判断的关系。"""


def flatten_cluster_groups(initial: list[ClusterRefinementItem], merged: list[ClusterRefinementItem],
                           original_indexes: set[int]) -> list[ClusterRefinementItem]:
    indexes = [i for item in merged for i in item.source_cluster_indexes]
    if len(indexes) != len(initial) or set(indexes) != set(range(len(initial))):
        raise ValueError("跨批归并遗漏、重复或引用未知观点方向")
    result = []
    for item in merged:
        parent_relations = {r.source_cluster_index: r.relation for r in item.source_relations}
        sources, relations = [], []
        for parent_index in item.source_cluster_indexes:
            parent = initial[parent_index]
            old_relations = {r.source_cluster_index: r.relation for r in parent.source_relations}
            for original_index in parent.source_cluster_indexes:
                sources.append(original_index)
                # Direction changes require the subsequent original-answer stance audit.
                # Do not infer support by flipping an earlier opposition label.
                relation = old_relations.get(original_index, 'related') if parent_relations.get(parent_index) == 'supports' else 'related'
                relations.append(ClusterSourceRelation(source_cluster_index=original_index, relation=relation))
        result.append(item.model_copy(update={'source_cluster_indexes': sources, 'source_relations': relations}))
    flattened = [i for item in result for i in item.source_cluster_indexes]
    if len(flattened) != len(original_indexes) or set(flattened) != original_indexes:
        raise ValueError("跨批归并后原始观点来源不完整或重复")
    return result
