function sha256(bytes){
    var k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],words=[],i,j,n=Math.ceil((bytes.length+9)/64)*16;
    if(bytes.length>16777216)throw Error('Vector source exceeds16MiB');
    for(i=0;i<n;i++)words[i]=0;
    for(i=0;i<bytes.length;i++)words[i>>2]|=(bytes.charCodeAt(i)&255)<<(24-(i%4)*8);
    words[bytes.length>>2]|=0x80<<(24-(bytes.length%4)*8);words[n-1]=bytes.length*8;
    function r(x,n){return (x>>>n)|(x<<(32-n));}
    for(i=0;i<n;i+=16){
        var w=[],a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
        for(j=0;j<64;j++){
            if(j<16)w[j]=words[i+j];else{var x=w[j-15],y=w[j-2];w[j]=(w[j-16]+(r(x,7)^r(x,18)^(x>>>3))+w[j-7]+(r(y,17)^r(y,19)^(y>>>10)))|0;}
            var t=(v+(r(e,6)^r(e,11)^r(e,25))+((e&f)^(~e&g))+k[j]+w[j])|0;
            var u=((r(a,2)^r(a,13)^r(a,22))+((a&b)^(a&c)^(b&c)))|0;
            v=g;g=f;f=e;e=(d+t)|0;d=c;c=b;b=a;a=(t+u)|0;
        }
        var state=[a,b,c,d,e,f,g,v];for(j=0;j<8;j++)h[j]=(h[j]+state[j])|0;
    }
    var result='';for(i=0;i<8;i++)result+=('00000000'+(h[i]>>>0).toString(16)).slice(-8);return result;
}
