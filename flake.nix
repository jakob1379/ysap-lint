{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
  };
  outputs = { self, nixpkgs, utils }: utils.lib.eachDefaultSystem (system:
    let
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python3;
      deps = ps: with ps; [ tree-sitter tree-sitter-bash pygls ];
      ysap-lint = python.pkgs.buildPythonApplication {
        pname = "ysap-lint";
        version = "0.1.0";
        pyproject = true;
        src = ./.;
        build-system = [ python.pkgs.setuptools ];
        dependencies = deps python.pkgs;
      };
    in
      {
        packages.default = ysap-lint;
        devShells.default = pkgs.mkShell {
          buildInputs = [
            (python.withPackages (ps: deps ps ++ [ ps.pytest ]))
          ];
        };
      }
  );
}
