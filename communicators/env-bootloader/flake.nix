{
  description = "Communicators – pure Nix development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python312;

          # Runtime dependencies mapped from your pyproject.toml.
          # Exact version pins from pyproject are not honored yet
          # (that requires a lockfile-based tool later).
          pythonEnv = python.withPackages (ps: with ps; [
            # aiohttp ecosystem
            aiohttp
            aiosignal
            attrs
            frozenlist
            multidict
            yarl
            aiohappyeyeballs
            propcache
            idna

            # HTTP client used by namespace / egg_transpiler / prefix
            httpx
            httpcore
            anyio
            sniffio
            certifi
            h11

            # websockets + typing
            websockets
            typing-extensions

            # scientific / plotting stack you currently depend on
            numpy
            scipy
            matplotlib
            pillow
            contourpy
            cycler
            fonttools
            kiwisolver
            pyparsing
            python-dateutil

            # misc
            packaging
            six
            pytz
            zope-interface
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              pythonEnv
            ];

            shellHook = ''
              # Make the local package importable with live changes.
              # Because the package lives at ./communicators, putting
              # the project root on PYTHONPATH is enough for:
              #   import communicators
              export PYTHONPATH="${toString ./.}:$PYTHONPATH"

              echo "→ Communicators pure Nix environment ready"
              echo "  Python      : $(python3 --version)"
              echo "  Local package: on PYTHONPATH (live editing)"
            '';
          };
        });
    };
}
