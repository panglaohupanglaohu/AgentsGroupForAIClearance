"""SkillRouter 状态硬过滤与 n-gram 检索测试 — 论文 Section 5.6。"""

import pytest

from agents.skill_router import SkillRouter


class DummySkillLibrary:
    def browse(self, team_id=None, visibility=None, category=None):
        return [
            {
                "skill_id": "sk_pub",
                "name": "Docker 容器发布与构建",
                "description": "用于构建 Docker 镜像并部署到集群",
                "category": "devops",
                "lifecycle_stage": "published",
                "instructions": "docker build -t app .",
            },
            {
                "skill_id": "sk_draft",
                "name": "Docker 容器本地调试草稿",
                "description": "本地调试 docker-compose",
                "category": "devops",
                "lifecycle_stage": "draft",
                "instructions": "docker-compose up",
            },
            {
                "skill_id": "sk_dep",
                "name": "旧版 Docker 废弃工具",
                "description": "废弃的部署脚本",
                "category": "devops",
                "lifecycle_stage": "deprecated",
                "instructions": "legacy script",
            },
        ]


def test_production_mode_hard_filters_draft_and_deprecated():
    router = SkillRouter(skill_library=DummySkillLibrary())
    
    # 生产模式: 仅允许 published / solidified
    session_prod = router.route("Docker 构建部署", production_only=True)
    returned_ids = [r.skill_id for r in session_prod.results]
    assert "sk_pub" in returned_ids
    assert "sk_draft" not in returned_ids
    assert "sk_dep" not in returned_ids
    assert session_prod.state_filter == "production_only"


def test_sandbox_mode_allows_draft_but_excludes_deprecated():
    router = SkillRouter(skill_library=DummySkillLibrary())
    
    # 默认/沙箱模式: 允许 draft, 绝不允许 deprecated
    session_sandbox = router.route("Docker", production_only=False)
    returned_ids = [r.skill_id for r in session_sandbox.results]
    assert "sk_pub" in returned_ids
    assert "sk_draft" in returned_ids
    assert "sk_dep" not in returned_ids


def test_char_ngram_calculation():
    ngrams = SkillRouter._char_ngrams("容器构建部署", n=3)
    assert "容器构" in ngrams
    assert "器构建" in ngrams
    assert "构建部" in ngrams

    score = SkillRouter._ngram_score("容器构建部署", "自动化容器构建流程", n=3)
    assert score > 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
