class ContentCaptureKit < Formula
  include Language::Python::Virtualenv

  desc "Get X, WeChat, and web articles as Markdown for knowledge bases"
  homepage "https://github.com/yanyansay/content-capture-kit"
  url "https://github.com/yanyansay/content-capture-kit.git",
      tag:      "v0.1.6",
      revision: "4535ecea907948c12dddc88479e38ce3d1df019b"
  head "https://github.com/yanyansay/content-capture-kit.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Get X, WeChat, and web articles", shell_output("#{bin}/content-capture --help")
  end
end
