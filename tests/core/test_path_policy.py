from governed_ai.core.domain.run.path_policy import sanitize_allowed_paths


def test_sanitize_allowed_paths_removes_control_plane_owned_grants() -> None:
    assert sanitize_allowed_paths(
        [
            "src/**",
            ".ai-team/evidence/**",
            ".ai-team/work-units/**",
            ".ai-team/state/**",
            ".ai-team/runs/**",
            ".ai-team/supervisor/**",
            ".ai-team/**",
            "**",
            "src/**",
        ]
    ) == ["src/**", ".ai-team/evidence/**"]
