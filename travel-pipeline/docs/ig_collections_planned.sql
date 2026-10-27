-- 인스타 쇼핑 A3 — 컬렉션 릴스 미리보기(기획 단계) 상태 추가. 여러 번 실행해도 안전.
-- ⚠️ 실행 순서: 이 SQL 먼저 → PR 머지.
alter table ig_collections drop constraint if exists ig_collections_status_check;
alter table ig_collections add constraint ig_collections_status_check
  check (status in ('planned', 'making', 'ok', 'failed', 'hidden'));
