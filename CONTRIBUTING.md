# Contributing

## Scope

이 저장소의 공개 surface는 code/ops mirror를 기준으로 운영한다.
기여는 주로 아래 경로를 대상으로 한다.

- `ops/`
- `tests/`
- `tools/`
- `.codex/agents/`
- `README.md`
- `ARCHITECTURE.md`
- `.github/`

다음 경로는 공개 기여 범위에서 제외한다.

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- generated private inventory/report artifact

## License of Contributions

- 별도 합의가 없는 한, 이 저장소에 의도적으로 제출한 기여는 root [LICENSE](./LICENSE)의 Apache-2.0 조건으로 배포되는 것으로 본다.
- third-party material을 가져올 때는 해당 라이선스 호환성과 attribution 필요 여부를 먼저 확인하고, 필요하면 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)도 함께 갱신한다.

## Development

1. `make dev-install`
2. `make static`
3. `make test`
4. 새 public 파일, 새 public prefix, 공개/비공개 경계를 바꾸는 변경이면 `make sync-public-policy`
5. 필요하면 `make public-export`
6. 공개 미러 자체가 self-contained인지 보려면 `make public-check`

full private vault를 가지고 작업하는 경우에는 추가로 `make check`를 사용할 수 있지만,
public mirror 기여 기본 gate는 `make static`과 `make test`다.

## Change Style

- 한 PR은 한 가지 목적에 집중하는 편이 좋다.
- schema를 바꾸면 관련 runtime과 test를 함께 갱신한다.
- generated private artifact를 source of truth처럼 커밋하지 않는다.
- run artifact, raw inventory, private corpus 내용은 public surface에 끌고 오지 않는다.
- subagent profile을 바꿀 때는 role intent와 ladder contract를 함께 검토한다.
- 외부 seed, snippet, template를 실질적으로 가져온 경우에는 출처와 라이선스 정보를 PR 설명에 적는다.
- 새 public 파일이나 공개 경계를 바꾸는 변경은 `make sync-public-policy`로 루트 `.gitignore` allowlist block을 policy source와 다시 맞춘다.

## Pull Requests

- 변경 이유와 범위를 PR 설명에 짧게 적는다.
- user-facing contract가 바뀌면 README 또는 관련 문서를 같이 갱신한다.
- regression risk가 있으면 어떤 테스트로 확인했는지 적는다.

## Security

보안 이슈는 공개 issue로 올리지 말고, 먼저 `SECURITY.md`의 안내를 따른다.
