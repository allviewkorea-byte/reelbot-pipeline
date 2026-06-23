-- music design_config (디자인 시스템 본부, 작업지시서 #35-A)
-- PLAY LIST 로고·Where 라벨의 폰트·크기·두께·색·투명도·테두리를 channel_status 행
-- (channel_id='rooftop_music')의 jsonb 컬럼 하나로 보관. 백곰 행에는 영향 없음(기본 빈 객체).
--
-- ⚠️ Supabase SQL 에디터에서 1회 수동 실행. GRANT 재부여 포함(불변원칙).

ALTER TABLE channel_status
  ADD COLUMN IF NOT EXISTS design_config jsonb NOT NULL DEFAULT '{}'::jsonb;

GRANT SELECT, INSERT, UPDATE ON channel_status TO anon, authenticated, service_role;

-- design_config 구조(rooftop_music) — 비어 있으면({}) 렌더는 현재 하드코딩값과 100% 동일:
-- {
--   "play_list":   { "font_family": "Playfair Display", "font_size": 324, "font_weight": 700,
--                    "color": "#FFFFFF", "opacity": 1.0,
--                    "border": { "enabled": false, "width": 2, "color": "#000000" } },
--   "where_label": { "font_family": "Inter", "font_size": 24, "font_weight": 600,
--                    "color": "#FFFFFF", "opacity": 0.9,
--                    "border": { "enabled": false, "width": 1, "color": "#000000" } }
-- }
