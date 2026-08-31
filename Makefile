# qPCR Agent 데모 — 자주 쓰는 명령 모음

.PHONY: run reset next-batch check

## 가상 실험실 서버 실행 (포트 8000, 대시보드: http://localhost:8000/dashboard)
run:
	uv run python -m server.main

## 실험 상태를 현재 주(batch)의 처음 상태로 초기화
reset:
	curl -X POST http://localhost:8000/admin/reset

## 다음 주 배치(week2) 투입 — stage6 무인 완주 시연 전에 실행
next-batch:
	curl -X POST http://localhost:8000/admin/next-batch

## stage 디렉터리 규격 검증
check:
	python3 scripts/check_stages.py
