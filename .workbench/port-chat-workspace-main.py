"""One-time test integration helper; removed before review."""
from pathlib import Path
import subprocess

def replace(text, old, new, count=1):
    assert text.count(old) == count, f"Expected {count} occurrences of {old[:80]!r}, got {text.count(old)}"
    return text.replace(old, new)

path = Path("apps/web/app/forma-workspace.tsx")
s = path.read_text()
s = replace(s, '                    placeholder={`Describe a change to ${activeNamespaceLabel.toLowerCase()}...`}', '                    aria-label={`Describe a change to ${activeNamespaceLabel.toLowerCase()}`}\n                    placeholder={`Describe a change to ${activeNamespaceLabel.toLowerCase()}...`}')
path.write_text(s)

path = Path("apps/web/e2e/opencode-chat.spec.ts")
s = path.read_text()
s = replace(s, '    const projectOutput = page.getByRole("region", { name: "Project", exact: true });', '    const projectOutput = page.getByTestId("project-pane");')
anchor = '    await test.step("New chat resets the rendered conversation with legacy hosted chat disabled", async () => {'
addition = '''    if (projectPublished) await test.step("the real OpenCode page shares one pane and preserves mobile drafts", async () => {
      const layout = page.getByTestId("chat-project-layout");
      await expect(layout).toHaveAttribute("data-layout", "split");
      await expect(projectOutput).toHaveCount(1);
      await expect(page.getByTestId("chat-pane").getByTestId("project-pane")).toHaveCount(0);
      await expect(page.getByTestId("chat-pane").locator("canvas")).toHaveCount(0);
      const currentCard = page.getByRole("button", { name: /View current project/ }).last();
      await expect(currentCard).toBeVisible();
      await page.getByRole("button", { name: "Close project", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await currentCard.click();
      await expect(projectOutput).toHaveCount(1);
      await page.getByRole("button", { name: "View project full screen", exact: true }).click();
      await expect(page.getByRole("dialog", { name: "Project workspace", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(layout).toHaveAttribute("data-layout", "split");
      await expect(projectOutput).toHaveCount(1);
      await page.screenshot({ path: `test-results/opencode-${resultMode}-workspace-desktop.png`, fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "Chat", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await followUpComposer.fill("Preserve this mobile draft");
      await page.getByRole("button", { name: "Show project", exact: true }).click();
      await expect(projectOutput).toHaveCount(1);
      await expect(page.getByTestId("chat-pane")).toBeHidden();
      await page.getByRole("button", { name: "Chat", exact: true }).click();
      await expect(projectOutput).toHaveCount(0);
      await expect(followUpComposer).toHaveValue("Preserve this mobile draft");
      await page.screenshot({ path: `test-results/opencode-${resultMode}-workspace-mobile.png`, fullPage: true });
      await followUpComposer.fill("");
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.getByRole("button", { name: "Show project", exact: true }).click();
      await expect(layout).toHaveAttribute("data-layout", "split");
    });

'''
s = replace(s, anchor, addition + anchor)
path.write_text(s)
subprocess.run(["git", "diff", "--check"], check=True)
