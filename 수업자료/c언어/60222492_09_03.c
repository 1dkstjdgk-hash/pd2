#include <stdio.h>
void main(){
	int n,i,r;
	r=1;
	for(i=2;i<=5;i++)
	{
		for(n=1;n<=i;n++)
		{
			r = r*n;
		}
		printf("%d!ÀÇ °á°ú:%d\n",i,r);
		r = 1;
	}
	
}
