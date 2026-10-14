{ pkgs, config, ... }:

{
  # Local environment for this AMP. Cloudera Machine Learning does not
  # read this file. The workbench runs the tasks in .project-metadata.yaml.
  # https://devenv.sh/reference/options/

  packages = with pkgs; [
    curl
    git
    just
  ];

  languages.python = {
    enable = true;
    package = pkgs.python312;
    uv.enable = true;
    uv.sync.enable = true;
    uv.sync.extras = [ "dev" ];
    venv.enable = true;
  };

  # One-shot: same script as the CML "Prepare project" job.
  processes.prepare = {
    exec = "python ${config.devenv.root}/1_job-prepare-project/job.py";
    restart.on = "never";
  };

  # Same script as the CML application. 8123 stays clear of the usual
  # 8080 listeners on a shared workstation. CML uses CDSW_APP_PORT.
  processes.app = {
    exec = "python ${config.devenv.root}/2_app-serve/app.py";
    env.PORT = "8123";
    after = [ "devenv:processes:prepare@completed" ];
    ready.http.get = {
      host = "127.0.0.1";
      port = 8123;
      path = "/health";
    };
    ready.period = 1;
    ready.probe_timeout = 2;
    ready.failure_threshold = 15;
    ready.timeout = 30;
  };

  enterShell = ''
    echo "optagent: $(python --version) — just test, devenv up (http://127.0.0.1:8123)"
  '';

  # devenv 2 runs this task during `devenv test`. The enterTest string
  # below is the same command for the shell-script test runner.
  tasks."devenv:enterTest" = {
    exec = "python -m pytest";
    showOutput = true;
  };

  enterTest = ''
    python -m pytest
  '';
}
