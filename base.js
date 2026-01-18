function getFloat(value, decimalPlaces = 2) {
  return parseFloat(value.toFixed(decimalPlaces));
}

function getParamByName(name, url) {
  if (!url)
    url = window.location.href;
  name = name.replace(/[\[\]]/g, '\\$&');
  let regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)', 'i');
  let match = regex.exec(url);
  if (!match)
    return null;
  if (!match[2])
    return '';
  return decodeURIComponent(match[2].replace(/\+/g, ' '));
}

function getRandomColor() {
  var letters = '0123456789ABCDEF';
  var color = '#';
  for (var i = 0; i < 6; i++) {
    color += letters[Math.floor(Math.random() * 16)];
  }
  return color;
}

function randomInt(max, min = 0) { return Math.round(Math.random() * (max - min)) + min; }
function randomFloat(max, min = 0) { return Math.random() * (max - min) + min; }
function randomElement(arr) { return arr[randomInt(arr.length - 1)]; }

function readFile(file, callback) {
  let xhr = new XMLHttpRequest();
  xhr.overrideMimeType('application/json');
  xhr.open('GET', file, true);
  xhr.onreadystatechange = function () {
    if (xhr.readyState === 4 && xhr.status == '200') {
      callback(xhr.responseText);
    }
  };
  xhr.send();
}

async function readFileAsync(file) {
  var xhr = new XMLHttpRequest();
  xhr.open("HEAD", file);
  //xhr.send();

  return new Promise(function (resolve, reject) {
    xhr.onreadystatechange = function () {
      if (xhr.readyState == 4) {
        if (xhr.status >= 300) {
          reject("Error, status code = " + xhr.status);
        } else {
          resolve(xhr.responseText);
        }
      }
    };
    xhr.overrideMimeType("application/json");
    xhr.open("get", file, true);
    xhr.send();
  });
}

/* Node.js specific code */
if (typeof module !== 'undefined' && module.exports) {
  const fs = require('fs');
  const path = require('path');
  const { spawn, execSync } = require('child_process');
  const os = require('os');

  async function send_email(subject, content, sender = '', to = '') {
    // Create PowerShell script to send email via Outlook
    const powershellScript = `
try {
    $outlook = New-Object -ComObject Outlook.Application
    $mail = $outlook.CreateItem(0)  # olMailItem = 0

    $mail.Subject = "${subject}"
    $mail.HTMLBody = @"
${content.replace(/"/g, '""')}
"@

    # Set recipient
    ${to ? `$mail.To = "${to}"` : ''}
    ${sender ? `$mail.SentOnBehalfOfName = "${sender}"` : ''}

    # Send the email automatically
    $mail.Send()

    Write-Host "Email sent successfully${to ? ' to ' + to : ''}"
    exit 0
} catch {
    Write-Host "Error sending email: $($_.Exception.Message)"
    exit 1
}`;

    const tempDir = os.tmpdir();
    const scriptPath = path.join(tempDir, `send-email-${Date.now()}.ps1`);

    try {
      fs.writeFileSync(scriptPath, powershellScript, 'utf8');

      return new Promise((resolve, reject) => {
        const powershell = spawn('powershell.exe', [
          '-ExecutionPolicy', 'Bypass',
          '-File', scriptPath
        ], {
          stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        powershell.stdout.on('data', (data) => {
          stdout += data.toString();
        });

        powershell.stderr.on('data', (data) => {
          stderr += data.toString();
        });

        powershell.on('close', (code) => {
          // Clean up temp file
          try {
            if (fs.existsSync(scriptPath)) {
              fs.unlinkSync(scriptPath);
            }
          } catch (e) {
            console.log('Note: Could not clean up temporary file:', e.message);
          }

          if (code === 0) {
            resolve(stdout.trim());
          } else {
            console.error('Failed to send email:', stderr.trim());
            reject(new Error(`PowerShell exited with code ${code}: ${stderr}`));
          }
        });

        powershell.on('error', (error) => {
          reject(error);
        });
      });

    } catch (error) {
      console.error('Error in send_email:', error);
      throw error;
    }
  }

  function _format_driver_date(dateString) {
    if (!dateString) return '';
    let datePart = dateString.toString().trim().split(/\s+/)[0];
    datePart = datePart.replace(/-/g, '/').replace(/\./g, '/');

    if (datePart.includes('/')) {
        const parts = datePart.split('/');
        if (parts.length === 3) {
            if (parts[0].length === 4 && !isNaN(parts[0])) {
                // YYYY/M/D -> YYYYMMDD
                return `${parts[0]}${parts[1].padStart(2, '0')}${parts[2].padStart(2, '0')}`;
            } else {
                // M/D/YYYY -> YYYYMMDD
                return `${parts[2]}${parts[0].padStart(2, '0')}${parts[1].padStart(2, '0')}`;
            }
        }
    }
    return datePart.replace(/\//g, '');
  }

  function _is_hardware_gpu(gpu) {
    const name = gpu.Name || '';
    const pnp = gpu.PNPDeviceID || '';
    const status = gpu.Status || '';
    if (name.includes('Microsoft') && (name.includes('Remote Display') || name.includes('Basic Display') || name.includes('Basic Render'))) return false;
    if (pnp.startsWith('SWD')) return false;
    if (status && !['ok', 'working properly', ''].includes(status.toLowerCase())) return false;
    return true;
  }

  function _is_software_gpu(gpu) {
    const name = gpu.Name || '';
    const status = gpu.Status || '';
    if (name.includes('Microsoft')) {
        if (name.includes('Remote Display')) return false;
        if (name.includes('Basic Display') || name.includes('Basic Render')) {
              if (!status || ['ok', 'working properly', ''].includes(status.toLowerCase())) return true;
        }
    }
    return false;
  }

  function _is_remote_display_gpu(gpu) {
    const name = gpu.Name || '';
    const status = gpu.Status || '';
    if (name.includes('Microsoft') && name.includes('Remote Display')) {
        if (!status || ['ok', 'working properly', ''].includes(status.toLowerCase())) return true;
    }
    return false;
  }

  function get_gpu_info() {
    let name = '';
    let driver_date = '';
    let driver_ver = '';
    let device_id = '';
    let vendor_id = '';

    if (os.platform() === 'win32') {
        try {
            const cmd = 'powershell -c "Get-CimInstance -query \'select * from win32_VideoController\' | Select-Object Name, @{N=\'DriverDate\';E={if($_.DriverDate){([datetime]$_.DriverDate).ToString(\'yyyy/MM/dd\')}}}, DriverVersion, PNPDeviceID, Status | ConvertTo-Json -Compress"';
            const output = execSync(cmd, { encoding: 'utf8' }).trim();

            if (output) {
                let gpus = [];
                try {
                    const parsed = JSON.parse(output);
                    gpus = Array.isArray(parsed) ? parsed : [parsed];
                } catch(e) {
                    // console.error('Failed to parse GPU info JSON', e);
                }

                let selectedGpu = null;

                // 1. Hardware
                for (const gpu of gpus) {
                    if (_is_hardware_gpu(gpu)) {
                        selectedGpu = gpu;
                        break;
                    }
                }

                // 2. Software
                if (!selectedGpu) {
                    for (const gpu of gpus) {
                        if (_is_software_gpu(gpu)) {
                            selectedGpu = gpu;
                            break;
                        }
                    }
                }

                // 3. Remote
                if (!selectedGpu) {
                    for (const gpu of gpus) {
                        if (_is_remote_display_gpu(gpu)) {
                            selectedGpu = gpu;
                            break;
                        }
                    }
                }

                if (selectedGpu) {
                    name = selectedGpu.Name || '';
                    driver_date = _format_driver_date(selectedGpu.DriverDate);
                    driver_ver = selectedGpu.DriverVersion || '';
                    const pnp = selectedGpu.PNPDeviceID || '';

                    if (pnp && !pnp.startsWith('SWD')) {
                        const devMatch = pnp.match(/DEV_(.{4})/);
                        const venMatch = pnp.match(/VEN_(.{4})/);
                        if (devMatch) device_id = devMatch[1];
                        if (venMatch) vendor_id = venMatch[1];
                    } else if (name.includes('Microsoft') && (name.includes('Basic Render') || name.includes('Basic Display') || name.includes('Remote Display'))) {
                          vendor_id = '1414';
                          if (name.includes('Basic Render')) device_id = '008c';
                          else if (name.includes('Basic Display')) device_id = '00ff';
                          else if (name.includes('Remote Display')) device_id = '008c';
                    }

                } else {
                      name = 'Microsoft Basic Render Driver';
                      vendor_id = '1414';
                      device_id = '008c';
                }
            }
        } catch (e) {
            console.error('Failed to get GPU info:', e.message);
        }
    }

    return { name, driver_date, driver_ver, device_id, vendor_id };
  }

  module.exports = {
    send_email,
    get_gpu_info
  };
}
