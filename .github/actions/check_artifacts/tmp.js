
function sleep(ms){ 
	return new Promise(resolve => setTimeout(resolve, ms));
}

(async function run() {
	console.log("hi");
	await sleep(1000);
	console.log("hi2");
})();

await sleep(1000);
console.log("hi3");