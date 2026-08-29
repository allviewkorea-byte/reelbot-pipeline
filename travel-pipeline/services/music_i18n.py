"""고정 문구 11개 언어 상수 — 번역 호출 없이 즉시 사용(비용 0, 실패 0).

본문 끝 고정 안내문(좋아하는 곡 질문 + 구독 유도)은 매 영상 동일하다. 이걸 매번 LLM 으로
번역하면 출력 토큰만 늘고(모델 상한 압박) 언어별 실패 가능성만 생긴다. 상수로 박아
번역 대상에서 제외한다. music_translate.generate_localizations(parts=...) 경로에서 사용.
"""

from __future__ import annotations

FIXED_OUTRO: dict[str, str] = {
    "ko": "🎵 가장 마음에 드는 노래는 무엇인가요?\n댓글로 알려주시면 다음 플리에 큰 도움이 됩니다 💚\n\n🔔 채널 구독하시면 매주 새로운 음악을 받아보실 수 있습니다 🔔",
    "en": "🎵 Which song is your favorite?\nLet us know in the comments — it really helps us plan the next playlist 💚\n\n🔔 Subscribe to get new music every week 🔔",
    "ja": "🎵 一番お気に入りの曲はどれですか？\nコメントで教えていただけると、次のプレイリスト作りの参考になります 💚\n\n🔔 チャンネル登録すると毎週新しい音楽が届きます 🔔",
    "zh": "🎵 你最喜欢哪一首？\n欢迎在评论区告诉我们，这对下一期歌单很有帮助 💚\n\n🔔 订阅频道，每周都能听到新音乐 🔔",
    "es": "🎵 ¿Cuál es tu canción favorita?\nCuéntanoslo en los comentarios: nos ayuda mucho con la próxima lista 💚\n\n🔔 Suscríbete y recibe música nueva cada semana 🔔",
    "pt": "🎵 Qual é a sua música favorita?\nConte para nós nos comentários — ajuda muito na próxima playlist 💚\n\n🔔 Inscreva-se e receba novas músicas toda semana 🔔",
    "ar": "🎵 ما هي أغنيتك المفضلة؟\nأخبرنا في التعليقات — هذا يساعدنا كثيرًا في قائمة التشغيل القادمة 💚\n\n🔔 اشترك في القناة لتصلك موسيقى جديدة كل أسبوع 🔔",
    "hi": "🎵 आपका पसंदीदा गाना कौन सा है?\nकमेंट में बताइए — इससे अगली प्लेलिस्ट बनाने में बहुत मदद मिलती है 💚\n\n🔔 चैनल सब्सक्राइब करें और हर हफ़्ते नया संगीत पाएँ 🔔",
    "th": "🎵 เพลงไหนที่คุณชอบที่สุด?\nบอกเราในคอมเมนต์ได้เลย มีประโยชน์มากสำหรับเพลย์ลิสต์ครั้งต่อไป 💚\n\n🔔 กดติดตามช่อง เพื่อรับเพลงใหม่ทุกสัปดาห์ 🔔",
    "tl": "🎵 Alin ang paborito mong kanta?\nSabihin mo sa comments — malaking tulong ito sa susunod naming playlist 💚\n\n🔔 Mag-subscribe para makatanggap ng bagong musika kada linggo 🔔",
    "vi": "🎵 Bài hát bạn thích nhất là bài nào?\nHãy cho chúng tôi biết ở phần bình luận — điều đó giúp ích rất nhiều cho playlist tiếp theo 💚\n\n🔔 Đăng ký kênh để nhận nhạc mới mỗi tuần 🔔",
}


def fixed_outro(lang: str) -> str:
    """해당 언어 고정 안내문. 없으면 영어 폴백."""
    return FIXED_OUTRO.get(lang) or FIXED_OUTRO["en"]
