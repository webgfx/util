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
