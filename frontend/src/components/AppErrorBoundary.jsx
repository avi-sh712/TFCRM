import { Component } from "react";

export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(previousProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="grid min-h-[60vh] place-items-center p-6">
        <section className="glass-card w-full max-w-lg rounded-lg">
          <h1 className="text-xl font-semibold">This workspace view could not load.</h1>
          <p className="mt-2 text-sm text-text-secondary">The rest of TalentForge is still available. Return to the dashboard or reload this view.</p>
          <button type="button" onClick={() => this.setState({ error: null })} className="mt-5 rounded-lg bg-accent-primary px-4 py-2 text-sm">Try again</button>
        </section>
      </main>
    );
  }
}
