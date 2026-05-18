class ContentCaptureKit < Formula
  include Language::Python::Virtualenv

  desc "Get X, WeChat, and web articles as Markdown for knowledge bases"
  homepage "https://github.com/yanyansay/content-capture-kit"
  url "https://github.com/yanyansay/content-capture-kit.git",
      tag:      "v0.1.7",
      revision: "b065aa3f3031093e96954cf3f169564b818986a0"
  head "https://github.com/yanyansay/content-capture-kit.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Get X, WeChat, and web articles", shell_output("#{bin}/content-capture --help")
  end
end
