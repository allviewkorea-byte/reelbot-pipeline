-- music channel_config (YouTube 메타데이터 풍부화, 작업지시서 #37)
-- 음악 채널 운영 정보(슬로건·소셜·AI 명시)를 channel_status 행(channel_id='rooftop_music')
-- 의 jsonb 컬럼 하나로 보관. 백곰 행에는 영향 없음(컬럼 기본값 빈 객체).
--
-- ⚠️ Supabase SQL 에디터에서 1회 수동 실행. GRANT 재부여 포함.

alter table public.channel_status
  add column if not exists channel_config jsonb default '{}'::jsonb;

grant all on table public.channel_status to service_role, anon, authenticated;

-- channel_config 구조(rooftop_music):
-- {
--   "slogan_en": "",
--   "slogan_kr": "",
--   "email": "",
--   "instagram": "",
--   "tiktok": "",
--   "spotify_url": "",
--   "ai_disclosure": "💿 모든 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다. 모든 이미지는 AI 생성 또는 라이선스 이미지를 사용합니다."
-- }
