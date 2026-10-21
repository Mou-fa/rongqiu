using System;
using System.Drawing;
using System.IO;
using System.Net;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace RongqiuWindow
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            string url = (args.Length > 0 && args[0].StartsWith("http")) ? args[0] : "http://127.0.0.1:8780";
            string dataDir = (args.Length > 1 && args[1].Length > 0)
                ? args[1]
                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Rongqiu", "webview2");
            Directory.CreateDirectory(dataDir);

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            var form = new Form
            {
                Text = "绒球",
                Width = 1120,
                Height = 820,
                MinimumSize = new Size(900, 640),
                StartPosition = FormStartPosition.CenterScreen,
                BackColor = Color.White
            };
            var view = new WebView2 { Dock = DockStyle.Fill };
            form.Controls.Add(view);

            var timer = new Timer { Interval = 2000 };
            timer.Tick += (s, e) =>
            {
                try
                {
                    var req = (HttpWebRequest)WebRequest.Create(url + "/api/app");
                    req.Timeout = 1500;
                    using (var resp = (HttpWebResponse)req.GetResponse()) { }
                }
                catch
                {
                    timer.Stop();
                    form.Close();
                }
            };

            form.Shown += async (s, e) =>
            {
                try
                {
                    var env = await CoreWebView2Environment.CreateAsync(null, dataDir);
                    await view.EnsureCoreWebView2Async(env);
                    var st = view.CoreWebView2.Settings;
                    st.AreDefaultContextMenusEnabled = false;
                    st.IsStatusBarEnabled = false;
                    st.AreDevToolsEnabled = false;
                    view.Source = new Uri(url);
                    timer.Start();
                }
                catch (Exception ex)
                {
                    MessageBox.Show("绒球窗口启动失败：" + ex.Message, "绒球",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                    form.Close();
                }
            };

            Application.Run(form);
        }
    }
}
