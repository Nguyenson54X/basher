{
  description = "basher - A CLI AI Agent";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        packages.default = pkgs.python3Packages.buildPythonApplication {
          pname = "basher";
          version = "0.1.0";
          src = ./.;

          format = "pyproject";

          nativeBuildInputs = with pkgs.python3Packages; [
            setuptools
          ];

          postInstall = ''
            mkdir -p $out/bin
            cp basher.py $out/bin/basher
            chmod +x $out/bin/basher
            patchShebangs $out/bin/basher
          '';

          meta = with pkgs.lib; {
            description = "A CLI AI Agent";
            mainProgram = "basher";
            platforms = platforms.all;
          };
        };

        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python3
          ];
        };
      }
    );
}
