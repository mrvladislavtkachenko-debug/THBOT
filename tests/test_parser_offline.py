"""Оффлайн-тест парсера на синтетическом HTML, повторяющем структуру t.me/s/."""
from thbot.parser import _parse_page, _parse_count, normalize_channel_ref, ChannelNotFoundError

HTML_SAMPLE = """
<div class="tgme_channel_info">
  <div class="tgme_channel_info_header"><div class="tgme_channel_info_header_title">Тестовый канал</div></div>
</div>
<a class="tme_messages_more" href="/s/test?before=100">earlier</a>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="test/105">
  <div class="tgme_widget_message_forwarded_from"><span>Forwarded from X</span></div>
  <div class="tgme_widget_message_text js-message_text">Рекламный пост: купите наш курс со скидкой!</div>
  <span class="tgme_widget_message_views">3.63K</span>
  <a class="tgme_widget_message_date" href="https://t.me/test/105"><time datetime="2026-08-24T05:58:37+00:00"></time></a>
  <div class="tgme_widget_message_reactions">
    <span class="tgme_widget_message_reaction"><i class="emoji">❤</i><b>7</b></span>
    <span class="tgme_widget_message_reaction"><i class="emoji">🔥</i><b>4</b></span>
  </div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="test/106">
  <div class="tgme_widget_message_text js-message_text">Чек-лист: как настроить CI за 30 минут. Шаг 1... Шаг 2... Сэкономили 10 часов в неделю.</div>
  <span class="tgme_widget_message_views">4.2K</span>
  <a class="tgme_widget_message_date" href="https://t.me/test/106"><time datetime="2026-08-25T08:17:42+00:00"></time></a>
  <div class="tgme_widget_message_reactions">
    <span class="tgme_widget_message_reaction"><i class="emoji">❤</i><b>28</b></span>
    <span class="tgme_widget_message_reaction"><i class="emoji">😁</i><b>22</b></span>
  </div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message service_message" data-post="test/107">
  <div class="tgme_widget_message_service"></div>
 </div>
</div>
"""


def test_parse_count():
    assert _parse_count("3.63K") == 3630
    assert _parse_count("1.2M") == 1_200_000
    assert _parse_count("4 800") == 4800
    assert _parse_count("12") == 12
    assert _parse_count(None) is None


def test_normalize():
    assert normalize_channel_ref("https://t.me/s/molyanov_blog") == "molyanov_blog"
    assert normalize_channel_ref("@durov") == "durov"
    assert normalize_channel_ref("t.me/durov/123") == "durov"
    assert normalize_channel_ref("molyanov_blog") == "molyanov_blog"
    try:
        normalize_channel_ref("просто текст")
        assert False, "ожидали ошибку"
    except ChannelNotFoundError:
        pass


def test_parse_page():
    posts, before = _parse_page(HTML_SAMPLE, "test")
    assert before == 100, before
    # служебный пост без текста отброшен
    assert len(posts) == 2, [p.id for p in posts]
    p105, p106 = posts
    assert p105.id == 105
    assert p105.views == 3630
    assert p105.reactions == {"❤": 7, "🔥": 4}
    assert p105.is_repost is True
    assert p105.date_iso == "2026-08-24T05:58:37+00:00"
    assert p106.views == 4200
    assert p106.reactions_total == 50
    assert "CI" in p106.text


if __name__ == "__main__":
    test_parse_count()
    test_normalize()
    test_parse_page()
    print("ALL PARSER TESTS OK")
