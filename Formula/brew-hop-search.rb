class BrewHopSearch < Formula
  include Language::Python::Virtualenv

  desc "Fast offline-first search of Homebrew formulae, casks, taps, and installed packages"
  homepage "https://github.com/mcint/brew-hop-search"
  url "https://files.pythonhosted.org/packages/source/b/brew-hop-search/brew_hop_search-0.2.0.tar.gz"
  sha256 "PLACEHOLDER"
  license "MIT"

  depends_on "python@3.12"

  resource "sqlite-utils" do
    url "https://files.pythonhosted.org/packages/source/s/sqlite-utils/sqlite_utils-3.38.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    virtualenv_install_with_resources
    bin.install_symlink "brew-hop-search" => "brewhs"
    bin.install_symlink "brew-hop-search" => "brew-hs" # `brew hs`
  end

  test do
    assert_match "brew-hop-search", shell_output("#{bin}/brew-hop-search --help")
  end
end
