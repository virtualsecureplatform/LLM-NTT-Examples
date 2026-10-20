"""II=1 elastic, bit-step constant remainders without inferred division."""


def latency(width, modulus):
    if modulus < 2 or width < modulus.bit_length():
        raise ValueError('remainder input must cover the modulus width')
    return width - modulus.bit_length() + 3


def emit(name, width, modulus, channels=2, signed=False):
    d=modulus.bit_length();stages=latency(width,modulus);remaining=width-d
    if channels<1:raise ValueError('at least one channel required')
    declarations=[];operations=[];outputs=[]
    for lane in range(channels):
        declarations.append(f'reg [{width-1}:0] magnitude{lane};')
        raw=f'in_data[{lane*width} +: {width}]'
        operations.append(f'magnitude{lane} <= '+(f'in_data[{(lane+1)*width-1}] ? -{raw} : {raw};' if signed else raw+';'))
        if signed:
            declarations.append(f'reg [{stages-2}:0] negative{lane};')
            operations.append(f'negative{lane} <= {{negative{lane}[{stages-3}:0],in_data[{(lane+1)*width-1}]}};')
        declarations.append(f'reg [{d-1}:0] remainder{lane}_0;')
        head=f'magnitude{lane}[{width-1} -: {d}]'
        operations.append(f"remainder{lane}_0 <= {head}>={d}'d{modulus} ? {head}-{d}'d{modulus} : {head};")
        if remaining:
            declarations.append(f'reg [{remaining-1}:0] tail{lane}_0;')
            operations.append(f'tail{lane}_0 <= magnitude{lane}[{remaining-1}:0];')
        for bit in range(remaining):
            candidate=f'step{lane}_{bit}'
            declarations.append(f'wire [{d}:0] {candidate}={{remainder{lane}_{bit},tail{lane}_{bit}[{remaining-bit-1}]}};')
            declarations.append(f'reg [{d-1}:0] remainder{lane}_{bit+1};')
            operations.append(f"remainder{lane}_{bit+1} <= {candidate}>={d+1}'d{modulus} ? {candidate}-{d+1}'d{modulus} : {candidate};")
            if remaining-bit>1:
                declarations.append(f'reg [{remaining-bit-2}:0] tail{lane}_{bit+1};')
                operations.append(f'tail{lane}_{bit+1} <= tail{lane}_{bit}[{remaining-bit-2}:0];')
        declarations.append(f'reg [{d-1}:0] result{lane};')
        r=f'remainder{lane}_{remaining}'
        value=f"negative{lane}[{stages-2}] && {r}!=0 ? {d}'d{modulus}-{r} : {r}" if signed else r
        operations.append(f'result{lane} <= {value};')
        outputs.append(f'assign out_data[{lane*d} +: {d}]=result{lane};')
    return f'''module {name}(input clock,reset,in_valid,output in_ready,
input [{channels*width-1}:0] in_data,output out_valid,input out_ready,output [{channels*d-1}:0] out_data);
reg [{stages-1}:0] valid;
wire advance=!valid[{stages-1}] || out_ready;
assign in_ready=advance;assign out_valid=valid[{stages-1}];
{''.join(declarations)}
{''.join(outputs)}
always @(posedge clock)begin
if(reset)valid<=0;
else if(advance)begin
valid<={{valid[{stages-2}:0],in_valid}};
{''.join(operations)}
end
end
endmodule'''
