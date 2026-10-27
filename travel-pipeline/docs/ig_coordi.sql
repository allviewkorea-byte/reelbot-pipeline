-- 인스타 쇼핑 A2-3a — 보세 상품 넣기 + AI 나머지 채우기 + 코디 자산 기록 + 내리기.
-- 기존 테이블은 컬럼 추가만(기존 행·API 호환). 새 테이블 ig_feedback 은 승인·반려·교체·내리기 이벤트.
--
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → PR 머지.
-- 백엔드는 secret(service_role) 키만 쓰므로 RLS 를 켜고 GRANT 는 service_role 에만.
-- 여러 번 실행해도 안전(if not exists / drop constraint if exists).

-- 레퍼런스 출처: 유튜브 썸네일 | 대표가 올린 스크린샷(분석용으로만 보관, 게시물 사용 금지)
alter table ig_refs add column if not exists source text not null default 'youtube';
alter table ig_refs drop constraint if exists ig_refs_source_check;
alter table ig_refs add constraint ig_refs_source_check check (source in ('youtube', 'screenshot'));

-- 상품 출처에 보세몰(대표가 넣은 사진·링크) 추가 + 쿠팡 이미지 삭제 시각 + 내리기
alter table ig_products drop constraint if exists ig_products_channel_check;
alter table ig_products add constraint ig_products_channel_check check (channel in ('coupang', 'naver', 'bose'));
alter table ig_products add column if not exists image_deleted_at timestamptz;  -- 쿠팡 약관 제5조: 쓰고 지움
alter table ig_products add column if not exists hidden_at timestamptz;
alter table ig_products add column if not exists hidden_reason text;

-- 룩 출처: 레퍼런스 분석 | 대표가 넣은 보세 상품 기준
alter table ig_looks add column if not exists source text not null default 'reference';
alter table ig_looks drop constraint if exists ig_looks_source_check;
alter table ig_looks add constraint ig_looks_source_check check (source in ('reference', 'bose'));

-- 착장 ↔ 룩 연결 + 대표 승인/반려 + 내리기 + 반응(B단계 인사이트 자리)
alter table ig_outfits add column if not exists look_id text references ig_looks(id);
alter table ig_outfits add column if not exists decision text;
alter table ig_outfits drop constraint if exists ig_outfits_decision_check;
alter table ig_outfits add constraint ig_outfits_decision_check check (decision is null or decision in ('approved', 'rejected'));
alter table ig_outfits add column if not exists decided_at timestamptz;
alter table ig_outfits add column if not exists hidden_at timestamptz;
alter table ig_outfits add column if not exists hidden_reason text;
alter table ig_outfits add column if not exists caption_note text;               -- "AI 가상 착용" 등 캡션용 문구
alter table ig_outfits add column if not exists insights jsonb;                  -- B단계: 인스타 반응
create index if not exists ig_outfits_look on ig_outfits (look_id);

-- 승인·반려·교체·내리기 이벤트(완전자동 전환 판단 근거 · SaaS 자산)
create table if not exists ig_feedback (
  id            bigint generated always as identity primary key,
  event         text not null check (event in ('approve', 'reject', 'swap', 'hide')),
  outfit_id     text references ig_outfits(id),
  look_id       text references ig_looks(id),
  product_id    bigint references ig_products(id),           -- 교체 전(또는 내린) 상품
  to_product_id bigint references ig_products(id),           -- 교체 후 상품
  item_index    int,
  reason        text,
  created_at    timestamptz not null default now()
);
create index if not exists ig_feedback_created on ig_feedback (created_at desc);

alter table ig_feedback enable row level security;
revoke all on table ig_feedback from anon, authenticated;
grant all on table ig_feedback to service_role;
