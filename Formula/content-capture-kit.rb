class ContentCaptureKit < Formula
  include Language::Python::Virtualenv

  desc "Get X, WeChat, and web articles as Markdown for knowledge bases"
  homepage "https://github.com/yanyansay/content-capture-kit"
  url "https://github.com/yanyansay/content-capture-kit.git",
      tag:      "v0.1.0",
      revision: "4c050ee99fbe0cfd0d617a839be32bf59fee92cd"
  head "https://github.com/yanyansay/content-capture-kit.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Get X, WeChat, and web articles", shell_output("#{bin}/content-capture --help")
  end
end
