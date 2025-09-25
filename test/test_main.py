"""
Tests for main entry point module.
"""

from unittest.mock import patch

from click.testing import CliRunner

from tim_mcp.main import cli, main
from tim_mcp.transport import HttpConfig, StdioConfig


class TestCli:
    """Tests for the Click CLI interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("tim_mcp.server.main")
    def test_cli_default_stdio(self, mock_server_main):
        """Test CLI with default STDIO transport."""
        result = self.runner.invoke(cli, [])

        # Should not exit with error
        assert result.exit_code == 0

        # Should call server_main with STDIO config
        mock_server_main.assert_called_once()
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, StdioConfig)
        assert transport_config.mode == "stdio"

    @patch("tim_mcp.server.main")
    def test_cli_http_default(self, mock_server_main):
        """Test CLI with HTTP transport using defaults."""
        result = self.runner.invoke(cli, ["--http"])

        assert result.exit_code == 0
        mock_server_main.assert_called_once()
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, HttpConfig)
        assert transport_config.mode == "http"
        assert transport_config.host == "127.0.0.1"
        assert transport_config.port == 8000

    @patch("tim_mcp.server.main")
    def test_cli_http_custom_port(self, mock_server_main):
        """Test CLI with HTTP transport and custom port."""
        result = self.runner.invoke(cli, ["--http", "--port", "9000"])

        assert result.exit_code == 0
        mock_server_main.assert_called_once()
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, HttpConfig)
        assert transport_config.port == 9000

    @patch("tim_mcp.server.main")
    def test_cli_http_custom_host(self, mock_server_main):
        """Test CLI with HTTP transport and custom host."""
        result = self.runner.invoke(cli, ["--http", "--host", "0.0.0.0"])

        assert result.exit_code == 0
        mock_server_main.assert_called_once()
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, HttpConfig)
        assert transport_config.host == "0.0.0.0"

    @patch("tim_mcp.server.main")
    def test_cli_http_custom_host_and_port(self, mock_server_main):
        """Test CLI with HTTP transport and custom host and port."""
        result = self.runner.invoke(
            cli, ["--http", "--host", "0.0.0.0", "--port", "9000"]
        )

        assert result.exit_code == 0
        mock_server_main.assert_called_once()
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, HttpConfig)
        assert transport_config.host == "0.0.0.0"
        assert transport_config.port == 9000

    def test_cli_host_without_http(self):
        """Test that --host without --http raises error."""
        result = self.runner.invoke(cli, ["--host", "0.0.0.0"])
        assert result.exit_code != 0
        assert "--host can only be used with --http" in result.output

    def test_cli_port_without_http(self):
        """Test that --port without --http raises error."""
        result = self.runner.invoke(cli, ["--port", "9000"])
        assert result.exit_code != 0
        assert "--port can only be used with --http" in result.output

    def test_cli_invalid_port_too_low(self):
        """Test that port below 1 raises error."""
        result = self.runner.invoke(cli, ["--http", "--port", "0"])
        assert result.exit_code != 0

    def test_cli_invalid_port_too_high(self):
        """Test that port above 65535 raises error."""
        result = self.runner.invoke(cli, ["--http", "--port", "65536"])
        assert result.exit_code != 0

    def test_cli_invalid_port_not_integer(self):
        """Test that non-integer port raises error."""
        result = self.runner.invoke(cli, ["--http", "--port", "abc"])
        assert result.exit_code != 0

    @patch("tim_mcp.server.main")
    def test_cli_log_level_debug(self, mock_server_main):
        """Test CLI with debug log level."""
        result = self.runner.invoke(cli, ["--log-level", "DEBUG"])

        assert result.exit_code == 0
        mock_server_main.assert_called_once()

    @patch("tim_mcp.server.main")
    def test_cli_log_level_case_insensitive(self, mock_server_main):
        """Test CLI with case insensitive log level."""
        result = self.runner.invoke(cli, ["--log-level", "debug"])

        assert result.exit_code == 0
        mock_server_main.assert_called_once()

    def test_cli_invalid_log_level(self):
        """Test that invalid log level raises error."""
        result = self.runner.invoke(cli, ["--log-level", "INVALID"])
        assert result.exit_code != 0

    @patch("tim_mcp.server.main")
    def test_cli_help(self, mock_server_main):
        """Test CLI help output."""
        result = self.runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "TIM-MCP: Terraform IBM Modules MCP Server" in result.output
        assert "Transport Modes:" in result.output
        assert "STDIO (default)" in result.output
        assert "HTTP: Runs as web server" in result.output
        assert "--http" in result.output
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--log-level" in result.output

    @patch("tim_mcp.server.main")
    def test_cli_keyboard_interrupt(self, mock_server_main):
        """Test CLI handles KeyboardInterrupt gracefully."""
        mock_server_main.side_effect = KeyboardInterrupt()

        result = self.runner.invoke(cli, [])
        assert result.exit_code == 0

    @patch("tim_mcp.server.main")
    def test_cli_exception_handling(self, mock_server_main):
        """Test CLI handles general exceptions."""
        mock_server_main.side_effect = Exception("Test error")

        result = self.runner.invoke(cli, [])
        assert result.exit_code == 1


class TestMainFunction:
    """Tests for the main() function wrapper."""

    @patch("tim_mcp.main.cli")
    def test_main_no_args(self, mock_cli):
        """Test main function with no arguments."""
        result = main()

        assert result == 0
        mock_cli.assert_called_once()

    @patch("tim_mcp.main.cli")
    def test_main_with_args(self, mock_cli):
        """Test main function with arguments."""
        result = main(["--http"])

        assert result == 0
        mock_cli.assert_called_once_with(args=["--http"], standalone_mode=False)

    @patch("tim_mcp.main.cli")
    def test_main_handles_system_exit(self, mock_cli):
        """Test main function handles SystemExit."""
        mock_cli.side_effect = SystemExit(1)

        result = main()
        assert result == 1

    @patch("tim_mcp.main.cli")
    def test_main_handles_system_exit_none_code(self, mock_cli):
        """Test main function handles SystemExit with None code."""
        mock_cli.side_effect = SystemExit(None)

        result = main()
        assert result == 0

    @patch("tim_mcp.main.cli")
    def test_main_handles_exception(self, mock_cli):
        """Test main function handles general exceptions."""
        mock_cli.side_effect = Exception("Test error")

        result = main()
        assert result == 1


class TestIntegration:
    """Integration tests for main entry point."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("tim_mcp.server.main")
    @patch("tim_mcp.main.logging.basicConfig")
    def test_integration_stdio_with_logging(self, mock_logging, mock_server_main):
        """Test full integration with STDIO mode and logging setup."""
        result = self.runner.invoke(cli, ["--log-level", "DEBUG"])

        assert result.exit_code == 0
        mock_logging.assert_called_once()
        mock_server_main.assert_called_once()

        # Check logging configuration
        logging_call = mock_logging.call_args
        assert logging_call[1]["level"] == 10  # DEBUG level

    @patch("tim_mcp.server.main")
    @patch("tim_mcp.main.logging.basicConfig")
    def test_integration_http_with_logging(self, mock_logging, mock_server_main):
        """Test full integration with HTTP mode and logging setup."""
        result = self.runner.invoke(
            cli,
            ["--http", "--host", "0.0.0.0", "--port", "9000", "--log-level", "WARNING"],
        )

        assert result.exit_code == 0
        mock_logging.assert_called_once()
        mock_server_main.assert_called_once()

        # Check transport configuration
        transport_config = mock_server_main.call_args[0][0]
        assert isinstance(transport_config, HttpConfig)
        assert transport_config.host == "0.0.0.0"
        assert transport_config.port == 9000

        # Check logging configuration
        logging_call = mock_logging.call_args
        assert logging_call[1]["level"] == 30  # WARNING level
