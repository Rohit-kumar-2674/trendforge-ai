# Generated reports

`trendforge report` and `trendforge update` write timestamped Markdown, JSON and HTML files here. Each report preserves the generation time, data mode, source freshness and limitations. Reports are also recorded in the database and downloadable from the dashboard.

Generated reports are ignored by Git because live reports can contain licensed provider data. There is no automatic public publishing. The provided daily workflow uploads demo/private-permitted reports as workflow artifacts; see [deployment](../docs/deployment.md).
