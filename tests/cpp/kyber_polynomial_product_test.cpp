#define KYBER_PE1_DATA_DIR "unused"
#define main original_reference_main
#include "kyber_pe1_reference_test.cpp"
#undef main

int modq(long long x) { x %= 3329; return x < 0 ? x + 3329 : x; }
int powq(int a, int n) { int v=1; for (;n;n>>=1,a=modq(a*a)) if(n&1)v=modq(v*a); return v; }
int reverse7(int n) { int r=0; for(int i=0;i<7;++i){r=2*r+(n&1);n>>=1;} return r; }
Poly quadratic_product(const Poly &a, const Poly &b) {
    Poly c{};
    for(int i=0;i<128;++i) {
        // FIPS 203: multiplication modulo X^2 - zeta^(2*BitRev7(i)+1).
        const int gamma=powq(17,2*reverse7(i)+1), j=2*i;
        c[j]=modq(static_cast<long long>(a[j])*b[j]+static_cast<long long>(gamma)*a[j+1]*b[j+1]);
        c[j+1]=modq(a[j]*b[j+1]+a[j+1]*b[j]);
    }
    return c;
}
Poly schoolbook(const Poly &a, const Poly &b) {
    long long sums[256]{};
    for(int i=0;i<256;++i)for(int j=0;j<256;++j)
        sums[(i+j)%256]+=(i+j>=256?-1LL:1LL)*a[i]*b[j];
    Poly c{};for(int i=0;i<256;++i)c[i]=modq(sums[i]);return c;
}
int main(int argc, char **argv) {
    Verilated::commandArgs(argc,argv);
    VKyberHPM1PE dut;reset(dut);unsigned state=17;
    for(int trial=0;trial<4;++trial) {
        Poly a{},b{};
        for(int i=0;i<256;++i) {
            state=1664525U*state+1013904223U;a[i]=state%3329;
            state=1664525U*state+1013904223U;b[i]=state%3329;
        }
        if(trial==0)a.fill(0);
        if(trial==1){a.fill(0);a[255]=1;b.fill(0);b[1]=1;}
        if(trial==2){a.fill(3328);for(int i=0;i<256;++i)b[i]=(i&1)?3328:0;}
        load_fntt(dut,a,false);load_fntt(dut,b,true);int wait=0;
        if(!start_and_wait(dut,false,false,wait))return 1;
        Poly fa=read_fntt(dut,false);
        if(!start_and_wait(dut,true,false,wait))return 1;
        Poly fb=read_fntt(dut,true),product=quadratic_product(fa,fb);
        load_intt(dut,product,false);
        if(!start_and_wait(dut,false,true,wait))return 1;
        if(!compare_poly("negacyclic product",read_intt(dut,false),schoolbook(a,b)))return 1;
    }
    dut.final();
    std::cout << "PASS 4 ML-KEM polynomial products: RTL NTT/INTT and host quadratic multiplication\n";
}
