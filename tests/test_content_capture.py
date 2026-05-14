from __future__ import annotations

import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from content_capture.assets import absolutize_local_asset_links, localize_markdown_assets
from content_capture.defuddle import parse_url_to_markdown, slug_from_url
from content_capture.cli import main
from content_capture.longform import longform_from_tweet
from content_capture.preview import markdown_to_preview_html
from content_capture.render import render_single_longform
from content_capture.wechat import extract_wechat_article_links
from content_capture.x_utils import extract_tweet_id, is_x_url
from content_capture.html_markdown import extract_article_markdown
from content_capture.xtomd import fetch_x_markdown_to_file


class ParsingTests(unittest.TestCase):
    def test_extracts_tweet_id_from_url_and_id(self) -> None:
        self.assertEqual(extract_tweet_id("1234567890"), "1234567890")
        self.assertEqual(extract_tweet_id("https://x.com/foo/status/987654321?s=20"), "987654321")
        self.assertEqual(extract_tweet_id("https://twitter.com/foo/statuses/111222333"), "111222333")

    def test_identifies_x_urls(self) -> None:
        self.assertTrue(is_x_url("https://x.com/jack/status/1"))
        self.assertFalse(is_x_url("https://example.com/a"))


class LongformTests(unittest.TestCase):
    def test_article_wins_over_note_tweet(self) -> None:
        post = longform_from_tweet(
            {
                "id": "1",
                "article": {"title": "Article title", "text": "Article body"},
                "note_tweet": {"text": "Note body"},
                "public_metrics": {"like_count": 3},
            },
            {"username": "alice", "name": "Alice"},
        )
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.source_kind, "article")
        self.assertEqual(post.title, "Article title")
        self.assertEqual(post.text, "Article body")
        self.assertIn("/alice/status/1", post.url)

    def test_note_tweet_is_longform(self) -> None:
        post = longform_from_tweet({"id": "2", "text": "short", "note_tweet": {"text": "Long note"}})
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.source_kind, "note_tweet")
        self.assertEqual(post.text, "Long note")

    def test_short_tweet_is_skipped(self) -> None:
        self.assertIsNone(longform_from_tweet({"id": "3", "text": "short"}))


class RenderAndDefuddleTests(unittest.TestCase):
    def test_render_single_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            post = longform_from_tweet(
                {"id": "1", "created_at": "2026-05-12T00:00:00Z", "note_tweet": {"text": "Body"}},
                {"username": "alice", "name": "Alice"},
            )
            assert post is not None
            path = render_single_longform(post, Path(temp_dir))
            content = path.read_text()
            self.assertIn("X Longform 1", content)
            self.assertIn("Source:", content)
            self.assertIn("Body", content)

    def test_defuddle_command_output_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.CompletedProcess(["defuddle"], 0, "# Title\n", "")
            with patch("shutil.which", return_value="/usr/local/bin/defuddle"):
                with patch("subprocess.run", return_value=completed) as run:
                    path = parse_url_to_markdown("https://example.com/a/b", Path(temp_dir))
            self.assertEqual(path.name, f"{slug_from_url('https://example.com/a/b')}.md")
            self.assertEqual(path.read_text(), "# Title\n")
            run.assert_called_once()

    def test_article_mirror_url_writes_under_tweet_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.CompletedProcess(["defuddle"], 0, "# Mirror\n\n```text\ncode\n```\n", "")
            with patch("shutil.which", return_value="/usr/local/bin/defuddle"):
                with patch("subprocess.run", return_value=completed):
                    status = main(
                        [
                            "article",
                            "https://x.com/alice/status/1234567890",
                            "--mirror-url",
                            "https://example.com/mirror",
                            "--out",
                            temp_dir,
                        ]
                    )
            path = Path(temp_dir) / "Mirror.md"
            self.assertEqual(status, 0)
            self.assertTrue(path.exists())
            content = path.read_text()
            self.assertIn("镜像: https://example.com/mirror", content)
            self.assertIn("```text", content)

    def test_extract_article_markdown_preserves_media_and_code(self) -> None:
        html = """
        <div class="markdown-body">
          <p><img src="/a.jpg" alt="A"></p>
          <p>Intro</p>
          <video src="/demo.mkv" controls></video>
          <h1>Prompt</h1>
          <shiki-code><pre><code>A [界面类型]
Line 2</code></pre></shiki-code>
        </div>
        <div>after</div>
        """
        markdown = extract_article_markdown(html, "https://example.com/post")
        self.assertIn("![A](https://example.com/a.jpg)", markdown)
        self.assertIn('<video src="https://example.com/demo.mkv" controls></video>', markdown)
        self.assertIn("```text\nA [界面类型]\nLine 2\n```", markdown)
        self.assertNotIn("after", markdown)

    def test_extract_article_markdown_ignores_wechat_video_iframe(self) -> None:
        html = r"""
        <div id="js_content">
          <p>Before</p>
          <iframe class="video_iframe rich_pages"
            data-src="https://mp.weixin.qq.com/mp/readtemplate?t=pages/video_player_tmpl&amp;action=mpvideo&amp;vid=wxv_1"
            data-mpvid="wxv_1"
            data-cover="http%3A%2F%2Fmmbiz.qpic.cn%2Fcover%2F0%3Fwx_fmt%3Djpeg"></iframe>
          <p>After</p>
        </div>
        <script>
        var videoPageInfos = [{
          video_id: 'wxv_1' || '',
          mp_video_trans_info: [{
            filesize: '100' * 1 || 0,
            url: ('http://mpvideo.qpic.cn/low.mp4?x=1').replace(/^http(s?):/, location.protocol)
          }, {
            filesize: '200' * 1 || 0,
            url: ('http://mpvideo.qpic.cn/high.mp4?x=1').replace(/^http(s?):/, location.protocol)
          }]
        }];
        window.__videoPageInfos = videoPageInfos;
        </script>
        """
        markdown = extract_article_markdown(html, "https://mp.weixin.qq.com/s/demo")
        self.assertIn("Before", markdown)
        self.assertIn("After", markdown)
        self.assertNotIn("<video", markdown)
        self.assertNotIn("mpvideo.qpic.cn", markdown)

    def test_extract_article_markdown_preserves_links(self) -> None:
        html = """
        <div id="js_content">
          <p>Read <a href="https://example.com/a">the article</a>.</p>
        </div>
        """
        markdown = extract_article_markdown(html, "https://mp.weixin.qq.com/s/demo")
        self.assertIn("[the article](https://example.com/a)", markdown)

    def test_extract_wechat_article_links_from_article_body(self) -> None:
        html = """
        <a href="https://mp.weixin.qq.com/s/outside">outside</a>
        <div id="js_content">
          <h2>需求</h2>
          <p><a href="https://mp.weixin.qq.com/s/child1?scene=1">Child One</a></p>
          <p><a data-link="/s/child2">Child Two</a></p>
          <p><a href="https://example.com/nope">External</a></p>
          <p><a href="https://mp.weixin.qq.com/s/child1?scene=1">Duplicate</a></p>
        </div>
        """
        links = extract_wechat_article_links(html, "https://mp.weixin.qq.com/s/root")
        self.assertEqual([link.url for link in links], ["https://mp.weixin.qq.com/s/child1?scene=1", "https://mp.weixin.qq.com/s/child2"])
        self.assertEqual([link.title for link in links], ["Child One", "Child Two"])
        self.assertEqual([link.section for link in links], ["需求", "需求"])

    def test_wechat_command_exports_seed_children_and_index(self) -> None:
        seed_html = """
        <meta property="og:title" content="Seed">
        <div id="js_content">
          <p>Seed body</p>
          <h2>需求</h2>
          <p><a href="https://mp.weixin.qq.com/s/child">Child Link</a></p>
        </div>
        """
        child_html = """
        <meta property="og:title" content="Child">
        <div id="js_content"><p>Child body</p></div>
        """

        def fake_fetch(url: str) -> str:
            if url == "https://mp.weixin.qq.com/s/root":
                return seed_html
            if url == "https://mp.weixin.qq.com/s/child":
                return child_html
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("content_capture.wechat.fetch_url_html", side_effect=fake_fetch):
                status = main(
                    [
                        "wechat",
                        "https://mp.weixin.qq.com/s/root",
                        "--out",
                        temp_dir,
                        "--no-local-assets",
                    ]
                )
            self.assertEqual(status, 0)
            category = Path(temp_dir) / "Seed"
            self.assertTrue((category / "微信文章知识库.md").exists())
            self.assertTrue((category / "Seed.md").exists())
            self.assertTrue((category / "需求" / "Child.md").exists())
            index = (category / "微信文章知识库.md").read_text(encoding="utf-8")
            self.assertIn("[[Seed]]", index)
            self.assertIn("[[需求/Child|Child]]", index)
            seed = (category / "Seed.md").read_text(encoding="utf-8")
            self.assertIn("[Child Link](需求/Child.md)", seed)
            self.assertNotIn("mp.weixin.qq.com/s/child", seed)

    def test_wechat_command_removes_spaces_from_paths(self) -> None:
        seed_html = """
        <meta property="og:title" content="Seed Title">
        <div id="js_content">
          <p>Seed body</p>
          <h2>Data Analysis</h2>
          <p><a href="https://mp.weixin.qq.com/s/child">Child Link</a></p>
        </div>
        """
        child_html = """
        <meta property="og:title" content="Child Title">
        <div id="js_content"><p>Child body</p></div>
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("content_capture.wechat.fetch_url_html", side_effect=[seed_html, child_html]):
                status = main(
                    [
                        "wechat",
                        "https://mp.weixin.qq.com/s/root",
                        "--out",
                        temp_dir,
                        "--no-local-assets",
                    ]
                )
            self.assertEqual(status, 0)
            paths = [path.relative_to(temp_dir).as_posix() for path in Path(temp_dir).rglob("*.md")]
            self.assertIn("SeedTitle/SeedTitle.md", paths)
            self.assertIn("SeedTitle/DataAnalysis/ChildTitle.md", paths)
            self.assertFalse(any(" " in path for path in paths))

    def test_localize_markdown_assets_downloads_and_rewrites_links(self) -> None:
        class FakeHeaders(dict):
            def get(self, key, default=None):
                return super().get(key.lower(), default)

        class FakeResponse:
            headers = FakeHeaders({"content-type": "image/png"})

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1) -> bytes:
                if getattr(self, "_read", False):
                    return b""
                self._read = True
                return b"asset"

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post.md"
            path.write_text(
                '![A](https://example.com/a)\n<video src="https://example.com/v.mkv" controls></video>\n',
                encoding="utf-8",
            )
            with patch.object(urllib.request, "urlopen", return_value=FakeResponse()):
                assets = localize_markdown_assets(path)
            content = path.read_text(encoding="utf-8")
            self.assertEqual(len(assets), 2)
            self.assertIn("![A](post/image-01-c4ed1c218d-a.png)", content)
            self.assertIn('<video src="post/video-02-e8c2c2c4a7-v.mkv" controls></video>', content)
            self.assertTrue((Path(temp_dir) / "post" / "image-01-c4ed1c218d-a.png").exists())

    def test_localize_markdown_assets_can_use_central_media_dirs(self) -> None:
        class FakeHeaders(dict):
            def get(self, key, default=None):
                return super().get(key.lower(), default)

        class FakeResponse:
            headers = FakeHeaders({"content-type": "image/png"})

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1) -> bytes:
                if getattr(self, "_read", False):
                    return b""
                self._read = True
                return b"asset"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "标题.md"
            path.write_text("![A](https://example.com/a)\n", encoding="utf-8")
            with patch.object(urllib.request, "urlopen", return_value=FakeResponse()):
                localize_markdown_assets(path, image_dir=root / "image", video_dir=root / "video")
            content = path.read_text(encoding="utf-8")
            self.assertIn("](image/image-01-c4ed1c218d-a.png)", content)
            self.assertTrue((root / "image" / "image-01-c4ed1c218d-a.png").exists())

    def test_localize_markdown_assets_retries_incomplete_downloads(self) -> None:
        class FakeHeaders(dict):
            def get(self, key, default=None):
                return super().get(key.lower(), default)

        class FakeResponse:
            headers = FakeHeaders({"content-type": "image/png", "content-length": "10"})

            def __init__(self, payload: bytes) -> None:
                self.payload = payload
                self._read = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1) -> bytes:
                if self._read:
                    return b""
                self._read = True
                return self.payload

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post.md"
            path.write_text("![A](https://example.com/a)\n", encoding="utf-8")
            responses = [FakeResponse(b"short"), FakeResponse(b"0123456789")]
            with patch.object(urllib.request, "urlopen", side_effect=responses) as urlopen:
                localize_markdown_assets(path)
            self.assertEqual(urlopen.call_count, 2)
            self.assertEqual((Path(temp_dir) / "post" / "image-01-c4ed1c218d-a.png").read_bytes(), b"0123456789")

    def test_absolutize_local_asset_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post.md"
            path.write_text('![A](post/a.jpg)\n<video src="post/v.mkv" controls></video>\n', encoding="utf-8")
            absolutize_local_asset_links(path)
            content = path.read_text(encoding="utf-8")
            self.assertIn(f"![A]({Path(temp_dir).resolve().as_posix()}/post/a.jpg)", content)
            self.assertIn(f'<video src="{Path(temp_dir).resolve().as_posix()}/post/v.mkv" controls></video>', content)

    def test_localize_video_uses_mp4_when_ffmpeg_conversion_succeeds(self) -> None:
        class FakeHeaders(dict):
            def get(self, key, default=None):
                return super().get(key.lower(), default)

        class FakeResponse:
            headers = FakeHeaders({"content-type": "video/x-matroska"})

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1) -> bytes:
                if getattr(self, "_read", False):
                    return b""
                self._read = True
                return b"video"

        def fake_run(args, **kwargs):
            Path(args[-1]).write_bytes(b"mp4")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post.md"
            path.write_text('<video src="https://example.com/v.mkv" controls></video>\n', encoding="utf-8")
            with patch.object(urllib.request, "urlopen", return_value=FakeResponse()):
                with patch("shutil.which", return_value="/usr/local/bin/ffmpeg"):
                    with patch("subprocess.run", side_effect=fake_run):
                        localize_markdown_assets(path)
            content = path.read_text(encoding="utf-8")
            self.assertIn('<video src="post/video-01-e8c2c2c4a7-v.mp4" controls></video>', content)

    def test_markdown_to_preview_html_renders_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post.md"
            path.write_text('# Title\n\n<video src="/tmp/demo.mp4" controls></video>\n', encoding="utf-8")
            html_path = markdown_to_preview_html(path)
            content = html_path.read_text(encoding="utf-8")
            self.assertIn('<video src="/tmp/demo.mp4" controls preload="metadata"></video>', content)
            self.assertIn('Open video file', content)

    def test_html_title_prefers_og_title(self) -> None:
        from content_capture.naming import html_title

        title = html_title('<meta property="og:title" content="Codex + image-2 视频产出工作流分享" />')
        self.assertEqual(title, "Codex + image-2 视频产出工作流分享")

    def test_xtomd_output_is_written_for_x_url(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return b"# X Article\n\nBody"

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
                path = fetch_x_markdown_to_file("https://x.com/alice/status/1234567890", Path(temp_dir))
            self.assertEqual(path.name, "1234567890.md")
            self.assertIn("Body", path.read_text())
            self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
