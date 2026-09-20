"""model_identity：模型实体注册表与解析（Task 07）。

模块边界（T07-2 契约）：
- provider_map：provider 双命名体系 → canonical providerId
- registry：Model Registry 加载（data/model-registry/models.json）
- resolver：严格解析（零 fuzzy；四态 resolved/family/ambiguous/unresolved）

哲学：零误绑优先于高解析率。
"""
